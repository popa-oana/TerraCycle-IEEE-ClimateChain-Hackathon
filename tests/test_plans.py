from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.main import app
from backend.rules.rotation import compute_plan_id, generate_rotations, score_sequence


def _override_db(session):
    def _get():
        yield session
    app.dependency_overrides[get_db] = _get


def _make_plan():
    return {
        "plan_id": "plan-test-001",
        "parcel_id": "parcel_01",
        "season_id": "season-2024",
        "crop_history": [{"year": 2023, "crop_id": "wheat"}],
        "treatments": [],
        "requested_crop_id": "peas",
        "rotations": [
            {
                "rotation_id": "rotation-01",
                "crops": [
                    {"year": 2025, "crop_id": "peas"},
                    {"year": 2026, "crop_id": "wheat"},
                    {"year": 2027, "crop_id": "sunflower"},
                ],
                "score": 0.95,
                "explanations": ["Alternation across demo crop groups."],
                "risks": [],
            }
        ],
        "climate_source": "fixture",
    }


def test_score_sequence_no_repeat():
    result = score_sequence("wheat", ["peas", "maize"])
    assert result["score"] == 100
    assert len(result["reasons"]) == 2


def test_score_sequence_same_crop_penalty():
    result = score_sequence("wheat", ["wheat", "peas"])
    assert result["score"] == 65
    assert any("repeating" in w for w in result["warnings"])


def test_score_sequence_same_family_penalty():
    result = score_sequence("wheat", ["maize", "peas"])
    assert result["score"] == 90
    assert any("family" in w for w in result["warnings"])


def test_generate_rotations_top_2():
    rotations = generate_rotations("peas", "wheat")
    assert len(rotations) == 2
    assert rotations[0]["score"] >= rotations[1]["score"]


def test_generate_rotations_deterministic():
    r1 = generate_rotations("peas", "wheat")
    r2 = generate_rotations("peas", "wheat")
    assert r1 == r2


def test_compute_plan_id_deterministic():
    req = {"parcel_id": "parcel_01", "season_id": "season-2024", "crop_history": [{"year": 2023, "crop_id": "wheat"}], "requested_crop_id": "peas"}
    assert compute_plan_id(req) == compute_plan_id(req)


def test_post_plans_success():
    plan = _make_plan()
    session = MagicMock()
    session.get.return_value = None
    _override_db(session)

    client = TestClient(app)
    res = client.post("/api/v1/plans", json={
        "parcel_id": "parcel_01",
        "season_id": "season-2024",
        "crop_history": [{"year": 2023, "crop_id": "wheat"}],
        "treatments": [],
        "requested_crop_id": "peas",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["plan_id"].startswith("plan-")
    assert len(data["rotations"]) == 2
    app.dependency_overrides.clear()


def test_post_plans_duplicate_years():
    session = MagicMock()
    _override_db(session)

    client = TestClient(app)
    res = client.post("/api/v1/plans", json={
        "parcel_id": "parcel_01",
        "season_id": "season-2024",
        "crop_history": [{"year": 2023, "crop_id": "wheat"}, {"year": 2023, "crop_id": "maize"}],
        "treatments": [],
        "requested_crop_id": "peas",
    })
    assert res.status_code == 422
    assert res.json()["detail"]["error"]["code"] == "VALIDATION_ERROR"
    app.dependency_overrides.clear()


def test_post_plans_existing_plan():
    plan = MagicMock()
    plan.plan_id = "plan-test-001"
    plan.parcel_id = "parcel_01"
    plan.season_id = "season-2024"
    plan.rotations = _make_plan()["rotations"]
    plan.climate_source = "fixture"
    session = MagicMock()
    session.get.return_value = plan
    _override_db(session)

    client = TestClient(app)
    res = client.post("/api/v1/plans", json={
        "parcel_id": "parcel_01",
        "season_id": "season-2024",
        "crop_history": [{"year": 2023, "crop_id": "wheat"}],
        "treatments": [],
        "requested_crop_id": "peas",
    })
    assert res.status_code == 200
    assert res.json()["plan_id"] == plan.plan_id
    app.dependency_overrides.clear()
