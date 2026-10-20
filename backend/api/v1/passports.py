import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Commitment, Transaction, Verdict

router = APIRouter(tags=["passports"])

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "demo.json"


def _load_parcel_info(parcel_id: str) -> dict:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for p in data.get("parcels", []):
        if p["parcel_id"] == parcel_id:
            return {
                "parcel_display_name": p.get("display_name", parcel_id),
                "region": p.get("region", "Unknown"),
            }
    return {"parcel_display_name": parcel_id, "region": "Unknown"}


@router.get("/passports/{commitment_id}")
def get_passport(commitment_id: str, db: Session = Depends(get_db)):
    commitment = db.get(Commitment, commitment_id)
    if not commitment:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "COMMITMENT_NOT_FOUND", "message": f"Commitment '{commitment_id}' does not exist."}},
        )

    verdict = db.query(Verdict).filter(Verdict.commitment_id == commitment_id).first()
    txs = db.query(Transaction).filter(Transaction.commitment_id == commitment_id).all()
    parcel_info = _load_parcel_info(commitment.parcel_id)

    tx_hashes = {}
    for tx in txs:
        key = tx.tx_type.replace("_commitment", "").replace("register", "register")
        tx_hashes[key] = tx.tx_hash

    return {
        "commitment_id": commitment.commitment_id,
        "parcel_display_name": parcel_info["parcel_display_name"],
        "region": parcel_info["region"],
        "season_id": commitment.season_id,
        "practice_type": "Vegetative Soil Cover",
        "plan_hash": commitment.plan_hash,
        "evidence_hash": verdict.evidence_hash if verdict else None,
        "verdict": verdict.verdict if verdict else None,
        "contract_state": commitment.state,
        "contract_address": None,
        "chain_id": 11155111,
        "observations_summary": None,
        "data_provenance": {
            "provider": "Copernicus Data Space",
            "dataset": "Sentinel-2 L2A",
            "bands": ["B04", "B08", "SCL"],
            "method": "Cloud-masked NDVI mean",
        } if verdict else None,
        "tx_hashes": tx_hashes or None,
        "limitations": [
            "NDVI measures vegetative reflectance proxy only; it cannot detect fertilizer dosage or herbicide absence.",
            "Demonstration represents a retrospective test using 2024 satellite observations, not a live future guarantee.",
            "Digital passport is an audit proof, not a certified organic label.",
        ],
    }
