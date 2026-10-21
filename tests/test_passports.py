from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.db import get_db
from backend.main import app


def _override_db(session):
    def _get():
        yield session
    app.dependency_overrides[get_db] = _get


def _make_commitment():
    m = MagicMock()
    m.commitment_id = "0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871"
    m.parcel_id = "parcel_01"
    m.season_id = "season-2024"
    m.plan_hash = "0x705b7a9dd94979bbc79a1af1a17b5aed531a3a3e7b27cb5a5f15635e1a1ee127"
    m.state = "negative"
    return m


def _make_verdict():
    v = MagicMock()
    v.evidence_hash = "0x89a43f3a2b84f44f4f8d12809d29a76c52769e62f05c759bc90c003ee3e9a16f"
    v.verdict = "nonconform"
    return v


def test_passport_not_found():
    session = MagicMock()
    session.get.return_value = None
    _override_db(session)

    client = TestClient(app)
    res = client.get("/api/v1/passports/0xnonexistent")
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "COMMITMENT_NOT_FOUND"
    app.dependency_overrides.clear()


def test_passport_found():
    commitment = _make_commitment()
    verdict = _make_verdict()

    session = MagicMock()
    session.get.return_value = commitment
    session.query.return_value.filter.return_value.first.return_value = verdict
    session.query.return_value.filter.return_value.all.return_value = []
    _override_db(session)

    client = TestClient(app)
    res = client.get(f"/api/v1/passports/{commitment.commitment_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["commitment_id"] == commitment.commitment_id
    assert data["parcel_display_name"] == "Field 01 — Dolj, Romania"
    assert data["plan_hash"] == commitment.plan_hash
    assert data["verdict"] == "nonconform"
    assert data["contract_state"] == "negative"
    assert len(data["limitations"]) == 3
    assert data["data_provenance"]["provider"] == "Copernicus Data Space"
    app.dependency_overrides.clear()


def test_passport_found_no_verdict():
    commitment = _make_commitment()

    session = MagicMock()
    session.get.return_value = commitment
    session.query.return_value.filter.return_value.first.return_value = None
    session.query.return_value.filter.return_value.all.return_value = []
    _override_db(session)

    client = TestClient(app)
    res = client.get(f"/api/v1/passports/{commitment.commitment_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["verdict"] is None
    assert data["evidence_hash"] is None
    app.dependency_overrides.clear()
