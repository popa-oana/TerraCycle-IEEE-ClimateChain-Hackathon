import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "climate"
API_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_climate(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    cache_id: str,
) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_id}.json"

    if cache_file.exists():
        logger.info("Climate cache hit: %s", cache_file)
        return json.loads(cache_file.read_text(encoding="utf-8"))

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "UTC",
        "models": "era5_land",
    }

    try:
        response = requests.get(API_URL, params=params, timeout=25)
        response.raise_for_status()
        result = response.json()
    except Exception as exc:
        logger.error("Climate fetch failed: %s", exc)
        raise RuntimeError(f"CLIMATE_FETCH_FAILED: {exc}") from exc

    if "daily" not in result or "time" not in result.get("daily", {}):
        raise RuntimeError("CLIMATE_FETCH_FAILED: unexpected API response shape")

    payload = {
        "source_url": response.url,
        "model": "era5_land",
        "timezone": "UTC",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "payload": result,
    }

    cache_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def get_climate_for_parcel(parcel_id: str, season_id: str, latitude: float, longitude: float) -> dict:
    cache_id = f"{parcel_id}_{season_id}"
    start = "2024-03-01"
    end = "2024-11-01"

    try:
        data = fetch_climate(latitude, longitude, start, end, cache_id)
        return {
            "source": data["source_url"],
            "model": data["model"],
            "fetched_at": data["fetched_at"],
            "summary": _summarize(data["payload"]),
        }
    except RuntimeError as exc:
        logger.warning("Climate unavailable, using fixture: %s", exc)
        return {
            "source": "fixture_fallback",
            "model": "era5_land",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "note": "Open-Meteo unavailable; using demo fixture values.",
                "mean_temperature_c": None,
                "total_precipitation_mm": None,
            },
        }


def _summarize(payload: dict) -> dict:
    daily = payload.get("daily", {})
    temps = daily.get("temperature_2m_mean", [])
    precips = daily.get("precipitation_sum", [])

    mean_temp = sum(t for t in temps if t is not None) / max(len([t for t in temps if t is not None]), 1)
    total_precip = sum(p for p in precips if p is not None)

    return {
        "mean_temperature_c": round(mean_temp, 2),
        "total_precipitation_mm": round(total_precip, 2),
    }
