import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.hashing import hash_snapshot
from backend.ml.rules import verify_parcel
from backend.models import Commitment, Verdict

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

    try:
        result = verify_parcel(
            parcel_id=commitment.parcel_id,
            policy=_load_policy(commitment.verification_policy_id),
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

    observations = result.get("observations", [])
    quality = result.get("quality", {})
    source = result.get("source", {})

    evidence_doc = {
        "commitment_id": commitment.commitment_id,
        "evidence_id": f"evidence-{commitment.parcel_id}-{commitment.season_id}",
        "verdict": result["verdict"],
        "verdict_code": result["verdict_code"],
        "reason_codes": [result.get("reason_code", "")] if result.get("reason_code") else [],
        "model_version": result.get("model", {}).get("model_version", "rule-based-v1"),
        "policy_version": commitment.verification_policy_id,
        "parcel_id": commitment.parcel_id,
        "season_id": commitment.season_id,
        "observations": {
            "total_observations": quality.get("total_rows", len(observations)),
            "valid_observations": quality.get("valid_count", len(observations)),
            "vegetated_count": sum(1 for o in observations if o.get("ndvi", 0) > 0.35),
            "vegetated_fraction": round(
                sum(1 for o in observations if o.get("ndvi", 0) > 0.35) / max(len(observations), 1), 4
            ),
        },
        "data_provenance": {
            "provider": source.get("provider", "unknown"),
            "dataset": source.get("dataset", "unknown"),
            "bands": ["B04", "B08", "SCL"],
            "method": "Cloud-masked NDVI mean",
        },
        "valid_until": commitment.settle_deadline,
    }

    evidence_bytes, evidence_hash = hash_snapshot(evidence_doc)

    attestation = {
        "commitmentId": commitment.commitment_id,
        "planHash": commitment.plan_hash,
        "evidenceHash": evidence_hash,
        "verdict": result["verdict_code"],
        "validUntil": commitment.settle_deadline,
    }

    signature = _sign_attestation(attestation)

    verdict = Verdict(
        evidence_id=evidence_doc["evidence_id"],
        commitment_id=commitment.commitment_id,
        evidence_hash=evidence_hash,
        evidence_snapshot=evidence_bytes,
        verdict=result["verdict"],
        verdict_code=result["verdict_code"],
        reason_codes=evidence_doc["reason_codes"],
        attestation=attestation,
        signature=signature,
        valid_until=commitment.settle_deadline,
        model_version=evidence_doc["model_version"],
        policy_version=evidence_doc["policy_version"],
    )
    db.add(verdict)
    db.commit()

    return {
        "commitment_id": commitment.commitment_id,
        "evidence_id": evidence_doc["evidence_id"],
        "evidence_hash": evidence_hash,
        "verdict": result["verdict"],
        "verdict_code": result["verdict_code"],
        "reason_codes": evidence_doc["reason_codes"],
        "attestation": attestation,
        "signature": signature,
        "snapshot_url": f"/api/v1/evidence/{evidence_doc['evidence_id']}/snapshot",
    }
