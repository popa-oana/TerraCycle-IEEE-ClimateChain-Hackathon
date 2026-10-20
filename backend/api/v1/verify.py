"""
backend/api/v1/verify.py — Satellite verification endpoint

Implements the POST /commitments/{commitment_id}/verify endpoint using the
canonical evidence builder from backend/services/evidence_builder.py.
"""
import hashlib
import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.hashing import hash_snapshot
from backend.ml.rules import verify_parcel
from backend.models import Commitment, Verdict
from backend.services.evidence_builder import (
    build_evidence_document,
    build_attestation,
    verify_evidence_document,
)

router = APIRouter(tags=["verify"])

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "demo.json"
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "ndvi"
SIGNER_SCRIPT = Path(__file__).resolve().parents[2] / "signer" / "sign_verdict.mjs"


def _load_policy(policy_id: str) -> dict:
    """Load verification policy from shared fixture."""
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    policies = data.get("verification_policies", {})
    policy = policies.get(policy_id)
    if not policy:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VALIDATION_ERROR", "message": f"Unknown policy '{policy_id}'."}},
        )
    return policy


def _sign_attestation(payload: dict) -> str:
    """Invoke the Node.js signer to produce an EIP-712 signature."""
    if not SIGNER_SCRIPT.exists():
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "SIGNING_FAILED", "message": "Node signer script not found."}},
        )
    try:
        completed = subprocess.run(
            ["node", str(SIGNER_SCRIPT)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "SIGNING_FAILED", "message": f"Signer unavailable: {exc}"}},
        ) from exc

    if completed.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "SIGNING_FAILED", "message": "Signer returned an error."}},
        )

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "SIGNING_FAILED", "message": "Signer output is not valid JSON."}},
        ) from exc

    signature = result.get("signature")
    if not signature:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "SIGNING_FAILED", "message": "Signer output missing signature."}},
        )
    return signature


@router.post("/commitments/{commitment_id}/verify")
def verify_commitment(commitment_id: str, db: Session = Depends(get_db)):
    """
    Verify a funded commitment using satellite evidence.

    Flow:
    1. Load commitment and validate state.
    2. Load verification policy from fixture.
    3. Call scientific verifier (verify_parcel).
    4. Build canonical evidence document using evidence builder.
    5. Validate evidence document against canonical schema.
    6. Canonicalize and hash evidence (SHA-256).
    7. Build EIP-712 attestation payload.
    8. Invoke Node signer for EIP-712 signature.
    9. Persist Verdict with evidence snapshot and signature.
    10. Return verification response with attestation and signature.
    """
    # 1. Load commitment and validate state
    commitment = db.get(Commitment, commitment_id)
    if not commitment:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "COMMITMENT_NOT_FOUND", "message": f"Commitment '{commitment_id}' does not exist."}},
        )

    if commitment.state != "funded":
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "INVALID_STATE", "message": f"Commitment must be funded to verify, current state: {commitment.state}."}},
        )

    # 2. Load verification policy
    policy = _load_policy(commitment.verification_policy_id)

    # 3. Call scientific verifier
    try:
        verifier_result = verify_parcel(
    if commitment.plan_snapshot is not None:
        recomputed_hash = "0x" + hashlib.sha256(commitment.plan_snapshot).hexdigest()
        if recomputed_hash != commitment.plan_hash:
            raise HTTPException(
                status_code=409,
                detail={"error": {"code": "PLAN_HASH_MISMATCH", "message": "The stored plan snapshot no longer matches the registered plan hash."}},
            )

    policy = _load_policy(commitment.verification_policy_id)

    try:
        result = verify_parcel(
            parcel_id=commitment.parcel_id,
            policy=policy,
            evidence_directory=str(EVIDENCE_DIR),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "INFERENCE_FAILED", "message": f"ML module error: {exc}"}},
        ) from exc

    # Validate verdict
    if verifier_result.get("verdict") not in ("conform", "nonconform", "inconclusive"):
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "INFERENCE_FAILED", "message": "ML module returned unexpected verdict."}},
        )

    # 4. Build canonical evidence document
    try:
        evidence_doc, evidence_bytes, evidence_hash = build_evidence_document(
            verifier_result=verifier_result,
            commitment=commitment,
            policy=policy,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "EVIDENCE_BUILD_FAILED", "message": f"Evidence document construction failed: {exc}"}},
        ) from exc

    # 5. Validate canonical evidence document
    try:
        verify_evidence_document(evidence_doc)
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "EVIDENCE_VALIDATION_FAILED", "message": f"Canonical evidence validation failed: {exc}"}},
        ) from exc

    # 6. Build EIP-712 attestation
    attestation = build_attestation(
        commitment=commitment,
        evidence_hash=evidence_hash,
        verdict_code=verifier_result["verdict_code"],
    )

    # 7. Invoke Node signer
    try:
        signature = _sign_attestation(attestation)
    except HTTPException:
        # Signer errors are already HTTPExceptions with proper codes
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "SIGNING_FAILED", "message": f"Signer invocation failed: {exc}"}},
        ) from exc

    # 8. Persist Verdict
    evidence_id = f"evidence-{commitment.parcel_id}-{commitment.season_id}"
    reason_codes = [verifier_result["reason_code"]] if verifier_result.get("reason_code") else []

    verdict = Verdict(
        evidence_id=evidence_id,
        commitment_id=commitment.commitment_id,
        evidence_hash=evidence_hash,
        evidence_snapshot=evidence_bytes,
        verdict=verifier_result["verdict"],
        verdict_code=verifier_result["verdict_code"],
        reason_codes=reason_codes,
        attestation=attestation,
        signature=signature,
        valid_until=commitment.settle_deadline,
        model_version=verifier_result["model"]["model_version"],
        policy_version=commitment.verification_policy_id,
    )
    db.add(verdict)
    db.commit()

    # 9. Return response
    return {
        "commitment_id": commitment.commitment_id,
        "evidence_id": evidence_id,
        "evidence_hash": evidence_hash,
        "verdict": verifier_result["verdict"],
        "verdict_code": verifier_result["verdict_code"],
        "reason_codes": reason_codes,
        "attestation": attestation,
        "signature": signature,
        "snapshot_url": f"/api/v1/evidence/{evidence_id}/snapshot",
    }
