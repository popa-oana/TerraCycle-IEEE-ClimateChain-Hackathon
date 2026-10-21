# -*- coding: utf-8 -*-
"""
tests/test_commitments_prepare.py — commitment preparation regression tests

Covers the bytes32 metadata resolution used by POST /api/v1/commitments/prepare:

- reference_parcel bytes32 metadata is merged into the matching parcels entry
- the season mapping of the reference parcel is correct
- other parcels keep their own mappings (no cross-parcel copying)
- existing parcel metadata is never overwritten by the merge
- missing / conflicting / unknown mappings still raise proper errors
- the endpoint returns a correctly computed commitment_id and plan_hash
"""
# -*- coding: utf-8 -*-
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Set up the test database BEFORE importing the app.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.main import app
from backend.db import get_db
from backend.models import Base, Parcel, Plan
from backend.api.v1.commitments import _get_bytes32, _load_bytes32_map
from backend.hashing import canonical_bytes, compute_commitment_id

FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "demo.json"

REFERENCE_PARCEL_ID = "parcel_01"
REFERENCE_PARCEL_B32 = "0x" + "1" * 64
REFERENCE_SEASON_B32 = "0x" + "2" * 64
REFERENCE_SEASON_ID = "season-2024"

BENEFICIARY = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


def _contains_float(value) -> bool:
    """True when a float is present at any nesting level."""
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_float(child) for child in value)
    return False


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ============================================================
# Bytes32 map resolution (unit level)
# ============================================================

class TestBytes32Map:
    def test_reference_parcel_receives_authoritative_bytes32(self):
        """parcel_01 inherits the bytes32 metadata of the authoritative fixture."""
        data = _fixture()
        ref = data["reference_parcel"]
        parcels = _load_bytes32_map()

        entry = parcels[REFERENCE_PARCEL_ID]
        assert entry["parcel_id_bytes32"] == ref["parcel_id_bytes32"]
        assert entry["season_id_bytes32"] == ref["season_id_bytes32"]
        assert entry["season_id"] == ref["season_id"]

    def test_reference_parcel_bytes32_match_expected_values(self):
        """The merged metadata is the expected bytes32 pair for parcel_01 / season-2024."""
        assert _get_bytes32(REFERENCE_PARCEL_ID, REFERENCE_SEASON_ID) == (
            REFERENCE_PARCEL_B32,
            REFERENCE_SEASON_B32,
        )

    def test_reference_commitment_id_is_reproduced(self):
        """The resolved bytes32 pair reproduces the commitment_id published in the fixture."""
        data = _fixture()
        parcel_b32, season_b32 = _get_bytes32(REFERENCE_PARCEL_ID, REFERENCE_SEASON_ID)
        assert compute_commitment_id(parcel_b32, season_b32) == data["reference_parcel"]["commitment_id"]

    def test_other_parcels_keep_their_own_mappings(self):
        """Other parcels keep their own bytes32 and never inherit the reference metadata."""
        data = _fixture()
        parcels = _load_bytes32_map()

        for parcel in data["parcels"]:
            if parcel["parcel_id"] == REFERENCE_PARCEL_ID:
                continue
            entry = parcels[parcel["parcel_id"]]
            assert entry["parcel_id_bytes32"] == parcel["parcel_id_bytes32"]
            assert entry["parcel_id_bytes32"] != REFERENCE_PARCEL_B32
            # No season bytes32 may be copied over from the reference parcel.
            assert "season_id_bytes32" not in entry

    def test_existing_parcel_metadata_is_not_overwritten(self):
        """The merge only adds missing identifiers; existing parcel metadata is preserved."""
        data = _fixture()
        ref = data["reference_parcel"]
        original = next(p for p in data["parcels"] if p["parcel_id"] == REFERENCE_PARCEL_ID)
        entry = _load_bytes32_map()[REFERENCE_PARCEL_ID]

        for key, value in original.items():
            assert entry[key] == value

        # The reference display_name / data_origin must not overwrite the parcels entry.
        assert entry["data_origin"] == original["data_origin"]
        assert entry["data_origin"] != ref["data_origin"]

    def test_unknown_parcel_raises_validation_error(self):
        """An unknown parcel has no bytes32 mapping."""
        with pytest.raises(HTTPException) as excinfo:
            _get_bytes32("parcel_99", REFERENCE_SEASON_ID)
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail["error"]["code"] == "VALIDATION_ERROR"

    def test_parcel_without_season_mapping_raises_validation_error(self):
        """parcel_02 has no season mapping, so it cannot be committed."""
        with pytest.raises(HTTPException) as excinfo:
            _get_bytes32("parcel_02", REFERENCE_SEASON_ID)
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail["error"]["code"] == "VALIDATION_ERROR"

    def test_unknown_season_raises_validation_error(self):
        """A season that is not the mapped season has no bytes32 mapping."""
        with pytest.raises(HTTPException) as excinfo:
            _get_bytes32(REFERENCE_PARCEL_ID, "season-2025")
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail["error"]["code"] == "VALIDATION_ERROR"

    def test_conflicting_bytes32_is_reported_not_overwritten(self, tmp_path, monkeypatch):
        """A conflicting identifier is reported instead of being silently overwritten."""
        from backend.api.v1 import commitments as commitments_module

        data = _fixture()
        data["parcels"][0]["parcel_id_bytes32"] = "0x" + "f" * 64
        conflicting = tmp_path / "conflicting.json"
        conflicting.write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setattr(commitments_module, "FIXTURE_PATH", conflicting)

        with pytest.raises(HTTPException) as excinfo:
            _load_bytes32_map()
        assert excinfo.value.status_code == 500
        assert excinfo.value.detail["error"]["code"] == "FIXTURE_CONFLICT"

    def test_conflicting_season_id_is_reported_not_overwritten(self, tmp_path, monkeypatch):
        """A season id that disagrees with the mapped season bytes32 is reported."""
        from backend.api.v1 import commitments as commitments_module

        data = _fixture()
        data["parcels"][0]["season_id"] = "season-2099"
        conflicting = tmp_path / "conflicting_season.json"
        conflicting.write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setattr(commitments_module, "FIXTURE_PATH", conflicting)

        with pytest.raises(HTTPException) as excinfo:
            _load_bytes32_map()
        assert excinfo.value.status_code == 500
        assert excinfo.value.detail["error"]["code"] == "FIXTURE_CONFLICT"


# ============================================================
# Endpoint level (POST /api/v1/commitments/prepare)
# ============================================================

@pytest.fixture()
def env(tmp_path):
    """Test client backed by an isolated SQLite database."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{(tmp_path / 'commitments.db').as_posix()}")
    session_factory = sessionmaker(bind=engine, autoflush=False)

    # SQLite has no regex operator, so the '~' check constraints must be dropped.
    saved = {table.name: table.constraints for table in Base.metadata.tables.values()}
    for table in Base.metadata.tables.values():
        table.constraints = [
            c for c in table.constraints
            if not hasattr(c, "sqltext") or "~" not in str(c.sqltext)
        ]
    try:
        Base.metadata.create_all(bind=engine)
    finally:
        for table in Base.metadata.tables.values():
            table.constraints = saved[table.name]

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, session_factory
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def _seed_plan(session_factory, parcel_id=REFERENCE_PARCEL_ID, season_id=REFERENCE_SEASON_ID) -> dict:
    """Insert a plan whose rotation carries no float field (canonical snapshot shape)."""
    plan_id = "plan-test-0001"
    rotation = {
        "rotation_id": "rotation-01",
        "crops": [
            {"year": 2025, "crop_id": "maize"},
            {"year": 2026, "crop_id": "sunflower"},
            {"year": 2027, "crop_id": "wheat"},
        ],
        "explanations": ["Rotation built from the crop history."],
        "risks": ["No significant risk identified."],
    }
    db = session_factory()
    try:
        db.add(
            Parcel(
                parcel_id=parcel_id,
                name=f"Field for {parcel_id}",
                geometry_path=f"data/parcels/{parcel_id}.geojson",
                area_ha=42.5,
            )
        )
        db.add(
            Plan(
                plan_id=plan_id,
                parcel_id=parcel_id,
                season_id=season_id,
                crop_history=[
                    {"year": 2022, "crop_id": "wheat"},
                    {"year": 2023, "crop_id": "sunflower"},
                ],
                treatments=[],
                requested_crop_id="maize",
                rotations=[rotation],
            )
        )
        db.commit()
    finally:
        db.close()
    return {"plan_id": plan_id, "rotation_id": rotation["rotation_id"], "rotation": rotation}


def _prepare(client, plan: dict) -> dict:
    response = client.post(
        "/api/v1/commitments/prepare",
        json={
            "plan_id": plan["plan_id"],
            "rotation_id": plan["rotation_id"],
            "beneficiary_address": BENEFICIARY,
            "verification_policy_id": "cover-v1",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestPrepareEndpoint:
    def test_prepare_returns_correct_commitment_id_and_plan_hash(self, env):
        """The prepared commitment carries the expected commitment_id and plan_hash."""
        client, session_factory = env
        data = _fixture()
        plan = _seed_plan(session_factory)

        payload = _prepare(client, plan)

        expected_commitment_id = compute_commitment_id(
            data["reference_parcel"]["parcel_id_bytes32"],
            data["reference_parcel"]["season_id_bytes32"],
        )
        assert payload["commitment_id"] == expected_commitment_id
        assert payload["commitment_id"] == data["reference_parcel"]["commitment_id"]
        assert payload["parcel_id"] == REFERENCE_PARCEL_ID
        assert payload["season_id"] == REFERENCE_SEASON_ID
        assert payload["state"] == "prepared"
        assert payload["beneficiary_address"] == BENEFICIARY
        assert payload["plan_hash"].startswith("0x")
        assert len(payload["plan_hash"]) == 66
        assert payload["snapshot_url"] == f"/api/v1/plans/{plan['plan_id']}/snapshot"

    def test_prepared_snapshot_hashes_to_plan_hash(self, env):
        """The stored canonical snapshot hashes to the returned plan_hash."""
        from backend.models import Commitment

        client, session_factory = env
        plan = _seed_plan(session_factory)
        payload = _prepare(client, plan)

        db = session_factory()
        try:
            stored = db.query(Commitment).filter(
                Commitment.commitment_id == payload["commitment_id"]
            ).one()
            assert "0x" + hashlib.sha256(stored.plan_snapshot).hexdigest() == payload["plan_hash"]
            snapshot = json.loads(stored.plan_snapshot.decode("utf-8"))
            assert snapshot["parcel_id"] == REFERENCE_PARCEL_ID
            assert snapshot["season_id"] == REFERENCE_SEASON_ID
            assert snapshot["plan_id"] == plan["plan_id"]
            assert snapshot["selected_rotation"] == plan["rotation"]
        finally:
            db.close()

    def test_prepare_is_idempotent_for_the_same_plan(self, env):
        """Preparing the same plan twice returns the same commitment."""
        client, session_factory = env
        plan = _seed_plan(session_factory)

        first = _prepare(client, plan)
        second = _prepare(client, plan)

        assert first["commitment_id"] == second["commitment_id"]
        assert first["plan_hash"] == second["plan_hash"]

    def test_prepare_for_parcel_without_season_mapping_returns_422(self, env):
        """A parcel without a bytes32 season mapping cannot be committed."""
        client, session_factory = env
        plan = _seed_plan(session_factory, parcel_id="parcel_02")

        response = client.post(
            "/api/v1/commitments/prepare",
            json={
                "plan_id": plan["plan_id"],
                "rotation_id": plan["rotation_id"],
                "beneficiary_address": BENEFICIARY,
                "verification_policy_id": "cover-v1",
            },
        )

        assert response.status_code == 422
        assert response.json()["detail"]["error"]["code"] == "VALIDATION_ERROR"

    def test_prepare_with_unknown_plan_returns_404(self, env):
        """An unknown plan id is rejected before any bytes32 lookup."""
        client, _ = env

        response = client.post(
            "/api/v1/commitments/prepare",
            json={
                "plan_id": "plan-does-not-exist",
                "rotation_id": "rotation-01",
                "beneficiary_address": BENEFICIARY,
                "verification_policy_id": "cover-v1",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"]["error"]["code"] == "PLAN_NOT_FOUND"


# ============================================================
# Full workflow: POST /plans -> POST /commitments/prepare
# ============================================================

def _create_plan_via_api(client, session_factory) -> dict:
    """Create a plan through the real plan-building path (POST /api/v1/plans)."""
    db = session_factory()
    try:
        db.add(
            Parcel(
                parcel_id=REFERENCE_PARCEL_ID,
                name="Field 01 — Dolj, Romania",
                geometry_path="data/parcels/parcel_01.geojson",
                area_ha=42.50,
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/plans",
        json={
            "parcel_id": REFERENCE_PARCEL_ID,
            "season_id": REFERENCE_SEASON_ID,
            "crop_history": [
                {"year": 2022, "crop_id": "wheat"},
                {"year": 2023, "crop_id": "sunflower"},
            ],
            "treatments": [],
            "requested_crop_id": "maize",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestPlanToCommitmentWorkflow:
    """The real workflow must not break on the floating-point rotation score."""

    def test_plans_endpoint_still_returns_the_float_score(self, env):
        """The score stays in the plan response: it is presentation metadata."""
        client, session_factory = env
        plan = _create_plan_via_api(client, session_factory)

        scores = [r["score"] for r in plan["rotations"]]
        assert scores, "the plan must offer rotations"
        assert all(isinstance(s, float) for s in scores)
        # Score-based ranking is preserved (best first).
        assert scores == sorted(scores, reverse=True)

    def test_plan_to_commitment_prepare_workflow_succeeds(self, env):
        """POST /plans -> POST /commitments/prepare completes and returns a valid hash."""
        from backend.models import Commitment

        client, session_factory = env
        data = _fixture()
        plan = _create_plan_via_api(client, session_factory)
        rotation = plan["rotations"][0]

        response = client.post(
            "/api/v1/commitments/prepare",
            json={
                "plan_id": plan["plan_id"],
                "rotation_id": rotation["rotation_id"],
                "beneficiary_address": BENEFICIARY,
                "verification_policy_id": "cover-v1",
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()

        # The commitment must use the authoritative parcel/season identifiers.
        assert payload["commitment_id"] == data["reference_parcel"]["commitment_id"]
        assert payload["commitment_id"] == compute_commitment_id(
            data["reference_parcel"]["parcel_id_bytes32"],
            data["reference_parcel"]["season_id_bytes32"],
        )
        assert payload["parcel_id"] == REFERENCE_PARCEL_ID
        assert payload["season_id"] == REFERENCE_SEASON_ID

        # The stored snapshot must be the exact bytes that were hashed.
        db = session_factory()
        try:
            stored = db.query(Commitment).filter(
                Commitment.commitment_id == payload["commitment_id"]
            ).one()
            snapshot_bytes = stored.plan_snapshot
        finally:
            db.close()

        assert "0x" + hashlib.sha256(snapshot_bytes).hexdigest() == payload["plan_hash"]

        # The stored snapshot must itself be canonical (re-serialising is identical).
        snapshot = json.loads(snapshot_bytes.decode("utf-8"))
        assert canonical_bytes(snapshot) == snapshot_bytes

        # No float may enter the canonical snapshot.
        assert _contains_float(snapshot) is False

    def test_canonical_snapshot_keeps_the_rotation_but_drops_the_score(self, env):
        """The selected rotation is signed; only the float ranking score is excluded."""
        from backend.models import Commitment

        client, session_factory = env
        plan = _create_plan_via_api(client, session_factory)
        rotation = plan["rotations"][0]

        response = client.post(
            "/api/v1/commitments/prepare",
            json={
                "plan_id": plan["plan_id"],
                "rotation_id": rotation["rotation_id"],
                "beneficiary_address": BENEFICIARY,
                "verification_policy_id": "cover-v1",
            },
        )
        assert response.status_code == 200, response.text

        db = session_factory()
        try:
            stored = db.query(Commitment).filter(
                Commitment.commitment_id == response.json()["commitment_id"]
            ).one()
            snapshot = json.loads(stored.plan_snapshot.decode("utf-8"))
        finally:
            db.close()

        signed_rotation = snapshot["selected_rotation"]
        assert signed_rotation["rotation_id"] == rotation["rotation_id"]
        assert signed_rotation["crops"] == rotation["crops"]
        assert signed_rotation["explanations"] == rotation["explanations"]
        assert signed_rotation["risks"] == rotation["risks"]
        assert "score" not in signed_rotation

        # Nothing else of the plan is dropped from the signed document.
        assert snapshot["plan_id"] == plan["plan_id"]
        assert snapshot["rotation_id"] == rotation["rotation_id"]
        assert snapshot["parcel_id"] == plan["parcel_id"]
        assert snapshot["season_id"] == plan["season_id"]
        assert snapshot["requested_crop_id"] == "maize"
        assert snapshot["beneficiary_address"] == BENEFICIARY
        assert snapshot["verification_policy_id"] == "cover-v1"
        assert snapshot["rules_version"] == "rotation-v1"
        assert snapshot["snapshot_version"] == "v1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
