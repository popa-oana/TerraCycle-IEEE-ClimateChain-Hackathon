# -*- coding: utf-8 -*-
"""
tests/test_seed_parcels.py — regression tests for the demo database seed.

The plans -> commitments workflow needs the `parcels` registry rows, otherwise
`plans.parcel_id` violates its foreign key. The seed takes them from the shared
fixture (data/fixtures/demo.json), the same source GET /api/v1/parcels uses.
"""
# -*- coding: utf-8 -*-
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "seed_parcels.py"
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "demo.json"


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_parcels", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    """An isolated database seeded through the real script."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.db import Base
    from backend.models import Parcel

    engine = create_engine(f"sqlite:///{(tmp_path / 'seed.db').as_posix()}")
    session_factory = sessionmaker(bind=engine, autoflush=False)

    # SQLite has no regex operator, so the '~' check constraints must be dropped.
    saved = {table.name: table.constraints for table in Base.metadata.tables.values()}
    for table in Base.metadata.tables.values():
        table.constraints = [
            c for c in table.constraints if not hasattr(c, "sqltext") or "~" not in str(c.sqltext)
        ]
    try:
        Base.metadata.create_all(bind=engine)
    finally:
        for table in Base.metadata.tables.values():
            table.constraints = saved[table.name]

    module = _load_seed_module()
    monkeypatch.setattr(module, "SessionLocal", session_factory)

    yield module, session_factory, Parcel

    engine.dispose()


class TestSeedParcels:
    def test_seed_inserts_every_fixture_parcel(self, seeded_db):
        module, session_factory, Parcel = seeded_db
        assert module.main() == 0

        session = session_factory()
        try:
            rows = session.query(Parcel).order_by(Parcel.parcel_id).all()
        finally:
            session.close()

        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["parcels"]
        assert len(rows) == len(fixture)
        by_id = {row.parcel_id: row for row in rows}
        for parcel in fixture:
            row = by_id[parcel["parcel_id"]]
            assert row.name == parcel["display_name"]
            assert row.geometry_path == parcel["geometry_url"].lstrip("/")
            assert float(row.area_ha) == float(parcel["area_ha"])

    def test_seed_is_idempotent(self, seeded_db):
        """Running the seed twice must not duplicate rows."""
        module, session_factory, Parcel = seeded_db
        assert module.main() == 0
        assert module.main() == 0

        session = session_factory()
        try:
            count = session.query(Parcel).count()
        finally:
            session.close()
        assert count == len(json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["parcels"])

    def test_seed_uses_the_shared_fixture(self, seeded_db):
        module, _, _ = seeded_db
        parcels = module.load_fixture_parcels()
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["parcels"]
        assert parcels == fixture

    def test_seeded_parcels_satisfy_the_plan_foreign_key(self, seeded_db):
        """A plan can reference a seeded parcel (the FK that blocked the demo)."""
        from sqlalchemy.exc import IntegrityError

        from backend.models import Plan

        module, session_factory, Parcel = seeded_db
        assert module.main() == 0

        session = session_factory()
        try:
            session.add(
                Plan(
                    plan_id="plan-seed-test",
                    parcel_id="parcel_01",
                    season_id="season-2024",
                    crop_history=[{"year": 2022, "crop_id": "wheat"}],
                    treatments=[],
                    requested_crop_id="maize",
                    rotations=[{"rotation_id": "rotation-01"}],
                )
            )
            session.commit()
            assert session.query(Plan).count() == 1
        finally:
            session.close()
