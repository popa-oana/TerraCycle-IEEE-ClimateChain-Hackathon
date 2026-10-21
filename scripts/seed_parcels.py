#!/usr/bin/env python
"""
scripts/seed_parcels.py — seed the `parcels` table from the shared fixture.

The demo database needs the parcel registry rows before the plans ->
commitments workflow can run: `plans.parcel_id` references `parcels.parcel_id`.
The rows come from data/fixtures/demo.json, the single source of truth used by
GET /api/v1/parcels, so the database and the API always agree.

The script is idempotent: running it twice updates the same rows instead of
duplicating them.

Usage:
    python scripts/seed_parcels.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "demo.json"

# backend.db builds its engine at import time, so the default must exist first.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from backend.db import SessionLocal  # noqa: E402
from backend.models import Parcel  # noqa: E402


def load_fixture_parcels() -> list[dict]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data.get("parcels", [])


def main() -> int:
    parcels = load_fixture_parcels()
    if not parcels:
        print(f"No parcels found in {FIXTURE_PATH}", file=sys.stderr)
        return 1

    session = SessionLocal()
    try:
        for parcel in parcels:
            geometry_path = str(parcel.get("geometry_url", "")).lstrip("/")
            existing = session.get(Parcel, parcel["parcel_id"])
            if existing is None:
                session.add(
                    Parcel(
                        parcel_id=parcel["parcel_id"],
                        name=parcel.get("display_name", parcel["parcel_id"]),
                        geometry_path=geometry_path,
                        area_ha=parcel.get("area_ha"),
                    )
                )
                action = "inserted"
            else:
                existing.name = parcel.get("display_name", existing.name)
                existing.geometry_path = geometry_path or existing.geometry_path
                existing.area_ha = parcel.get("area_ha", existing.area_ha)
                action = "updated"
            print(f"  {action}: {parcel['parcel_id']} -> {parcel.get('display_name', '')}")
        session.commit()
    except Exception as exc:  # noqa: BLE001 - the CLI must fail loudly
        session.rollback()
        print(f"Seeding failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    print(f"Seeded {len(parcels)} parcel(s) from {FIXTURE_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
