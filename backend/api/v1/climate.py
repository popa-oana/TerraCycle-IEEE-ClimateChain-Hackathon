import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.services.climate_service import get_climate_for_parcel

router = APIRouter(tags=["climate"])

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "demo.json"


def _get_parcel_coords(parcel_id: str) -> tuple[float, float]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for p in data.get("parcels", []):
        if p["parcel_id"] == parcel_id:
            return p["latitude"], p["longitude"]
    raise HTTPException(
        status_code=404,
        detail={"error": {"code": "PARCEL_NOT_FOUND", "message": f"Parcel '{parcel_id}' not found."}},
    )


@router.get("/climate/{parcel_id}/{season_id}")
def get_climate(parcel_id: str, season_id: str):
    lat, lon = _get_parcel_coords(parcel_id)
    climate = get_climate_for_parcel(parcel_id, season_id, lat, lon)
    return climate
