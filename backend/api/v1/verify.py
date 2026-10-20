import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.ml.rules import verify_parcel
from backend.models import Commitment, Verdict
from backend.services.evidence_builder import build_attestation, build_evidence_document

router = APIRouter(tags=["verify"])

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "demo.json"
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "ndvi"
SIGNER_SCRIPT = Path(__file__).resolve().parents[2] / "signer" / "sign_verdict.mjs"


def _load_policy(policy_id: str) -> dict:
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

    if result.get("verdict") not in ("conform", "nonconform", "inconclusive"):
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "INFERENCE_FAILED", "message": "ML module returned unexpected verdict."}},
        )

    try:
        evidence_doc, evidence_bytes, evidence_hash = build_evidence_document(
            verifier_result=result,
            commitment=commitment,
            policy=policy,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "INFERENCE_FAILED", "message": f"Evidence building failed: {exc}"}},
        ) from exc

    attestation = build_attestation(
        commitment=commitment,
        evidence_hash=evidence_hash,
        verdict_code=result["verdict_code"],
    )

    signature = _sign_attestation(attestation)

    verdict = Verdict(
        evidence_id=f"evidence-{commitment.parcel_id}-{commitment.season_id}",
        commitment_id=commitment.commitment_id,
        evidence_hash=evidence_hash,
        evidence_snapshot=evidence_bytes,
        verdict=result["verdict"],
        verdict_code=result["verdict_code"],
        reason_codes=[result["reason_code"]] if result.get("reason_code") else [],
        attestation=attestation,
        signature=signature,
        valid_until=commitment.settle_deadline,
        model_version=result.get("model", {}).get("model_version", "rule-based-v1"),
        policy_version=commitment.verification_policy_id,
    )
    db.add(verdict)
    db.commit()

    return {
        "commitment_id": commitment.commitment_id,
        "evidence_id": verdict.evidence_id,
        "evidence_hash": evidence_hash,
        "verdict": result["verdict"],
        "verdict_code": result["verdict_code"],
        "reason_codes": [result["reason_code"]] if result.get("reason_code") else [],
        "attestation": attestation,
        "signature": signature,
        "snapshot_url": f"/api/v1/evidence/{verdict.evidence_id}/snapshot",
    }
