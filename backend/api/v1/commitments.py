import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.hashing import compute_commitment_id, hash_snapshot
from backend.models import Commitment, Transaction, Verdict
from backend.schemas import PrepareRequest, PrepareResponse

router = APIRouter(tags=["commitments"])

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "demo.json"
SETTLE_DAYS = 30


def _load_bytes32_map() -> dict[str, dict]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    parcels = {p["parcel_id"]: p for p in data.get("parcels", [])}
    ref = data.get("reference_parcel", {})
    parcels.setdefault(ref.get("parcel_id", ""), ref)
    return parcels


def _get_bytes32(parcel_id: str, season_id: str) -> tuple[str, str]:
    data = _load_bytes32_map()
    p = data.get(parcel_id, {})
    parcel_b32 = p.get("parcel_id_bytes32")
    season_b32 = p.get("season_id_bytes32")
    if not parcel_b32 or not season_b32:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VALIDATION_ERROR", "message": f"No bytes32 mapping for parcel '{parcel_id}' or season '{season_id}'."}},
        )
    return parcel_b32, season_b32


@router.post("/commitments/prepare", response_model=PrepareResponse)
def prepare_commitment(request: PrepareRequest, db: Session = Depends(get_db)):
    from backend.models import Plan

    plan = db.get(Plan, request.plan_id)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "PLAN_NOT_FOUND", "message": f"Plan '{request.plan_id}' does not exist."}},
        )

    rotation = next((r for r in plan.rotations if r.get("rotation_id") == request.rotation_id), None)
    if not rotation:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VALIDATION_ERROR", "message": f"Rotation '{request.rotation_id}' not found in plan."}},
        )

    parcel_b32, season_b32 = _get_bytes32(plan.parcel_id, plan.season_id)
    commitment_id = compute_commitment_id(parcel_b32, season_b32)

    existing = db.get(Commitment, commitment_id)
    if existing:
        return PrepareResponse(
            commitment_id=existing.commitment_id,
            plan_hash=existing.plan_hash,
            parcel_id=existing.parcel_id,
            season_id=existing.season_id,
            beneficiary_address=existing.beneficiary_address,
            settle_deadline=str(existing.settle_deadline),
            snapshot_url=f"/api/v1/plans/{existing.plan_id}/snapshot",
            state=existing.state,
        )

    snapshot_doc = {
        "parcel_id": plan.parcel_id,
        "season_id": plan.season_id,
        "plan_id": plan.plan_id,
        "rotation_id": request.rotation_id,
        "crop_history": plan.crop_history,
        "treatments": plan.treatments,
        "requested_crop_id": plan.requested_crop_id,
        "selected_rotation": rotation,
        "beneficiary_address": request.beneficiary_address,
        "verification_policy_id": request.verification_policy_id,
        "rules_version": "rotation-v1",
        "snapshot_version": "v1",
    }

    snapshot_bytes, plan_hash = hash_snapshot(snapshot_doc)
    settle_deadline = int(time.time()) + SETTLE_DAYS * 86400

    commitment = Commitment(
        commitment_id=commitment_id,
        plan_id=plan.plan_id,
        parcel_id=plan.parcel_id,
        season_id=plan.season_id,
        rotation_id=request.rotation_id,
        verification_policy_id=request.verification_policy_id,
        beneficiary_address=request.beneficiary_address,
        plan_hash=plan_hash,
        plan_snapshot=snapshot_bytes,
        settle_deadline=settle_deadline,
        state="prepared",
    )
    db.add(commitment)
    db.commit()

    return PrepareResponse(
        commitment_id=commitment.commitment_id,
        plan_hash=commitment.plan_hash,
        parcel_id=commitment.parcel_id,
        season_id=commitment.season_id,
        beneficiary_address=commitment.beneficiary_address,
        settle_deadline=str(commitment.settle_deadline),
        snapshot_url=f"/api/v1/plans/{plan.plan_id}/snapshot",
        state=commitment.state,
    )


@router.get("/commitments/{commitment_id}")
def get_commitment(commitment_id: str, db: Session = Depends(get_db)):
    commitment = db.get(Commitment, commitment_id)
    if not commitment:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "COMMITMENT_NOT_FOUND", "message": f"Commitment '{commitment_id}' does not exist."}},
        )

    txs = db.query(Transaction).filter(Transaction.commitment_id == commitment_id).all()
    verdict = db.query(Verdict).filter(Verdict.commitment_id == commitment_id).first()

    return {
        "commitment_id": commitment.commitment_id,
        "state": commitment.state,
        "parcel_id": commitment.parcel_id,
        "season_id": commitment.season_id,
        "plan_hash": commitment.plan_hash,
        "beneficiary_address": commitment.beneficiary_address,
        "settle_deadline": str(commitment.settle_deadline),
        "transactions": [
            {
                "tx_hash": tx.tx_hash,
                "tx_type": tx.tx_type,
                "status": tx.status,
                "block_number": tx.block_number,
            }
            for tx in txs
        ],
        "verdict": (
            {
                "evidence_id": verdict.evidence_id,
                "verdict": verdict.verdict,
                "verdict_code": verdict.verdict_code,
                "reason_codes": verdict.reason_codes,
            }
            if verdict
            else None
        ),
    }
