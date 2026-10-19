import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["parcels"])

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "demo.json"


def _load_parcels() -> list[dict]:
    if not FIXTURE_PATH.exists():
        raise HTTPException(status_code=500, detail={"error": {"code": "FIXTURE_NOT_FOUND", "message": "Parcel fixture file not found."}})
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data.get("parcels", [])


@router.get("/parcels")
def list_parcels():
    return {"parcels": _load_parcels()}
