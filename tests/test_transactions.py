"""Integration tests for POST /commitments/{id}/transactions endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import get_db
from backend.models import Commitment, Transaction


def test_transactions_not_found():
    session = MagicMock()
    session.get.return_value = None

    def override_db():
        yield session
    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    res = client.post(
        "/api/v1/commitments/0xnonexistent/transactions?tx_hash=0xabc&tx_type=register_commitment",
    )
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "COMMITMENT_NOT_FOUND"
    app.dependency_overrides.clear()


def test_transactions_idempotent():
    commitment = MagicMock()
    commitment.commitment_id = "0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871"
    commitment.state = "funded"
    commitment.parcel_id = "parcel_01"
    commitment.season_id = "season-2024"
    commitment.plan_hash = "0x705b7a9dd94979bbc79a1af1a17b5aed531a3a3e7b27cb5a5f15635e1a1ee127"

    existing_tx = MagicMock()
    existing_tx.tx_hash = "0xabc"
    existing_tx.commitment_id = "0x3e92..."
    existing_tx.tx_type = "register_commitment"
    existing_tx.status = "confirmed"
    existing_tx.block_number = 123
    existing_tx.checks_passed = ["network_matches"]

    def get_side_effect(model, id):
        if model is Commitment:
            return commitment
        if model is Transaction and id == "0xabc":
            return existing_tx
        return None

    session = MagicMock()
    session.get.side_effect = get_side_effect

    def override_db():
        yield session
    from backend.db import get_db
    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    with patch("backend.api.v1.transactions.verify_transaction") as mock_verify, \
         patch("backend.api.v1.transactions.create_web3") as mock_create_web3:
        mock_verify.return_value = {
            "tx_hash": "0xabc",
            "tx_type": "register_commitment",
            "status": "confirmed",
            "block_number": 123,
            "checks_passed": ["network_matches"],
        }
        mock_create_web3.return_value = MagicMock()
        res = client.post(
            "/api/v1/commitments/0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871/transactions?tx_hash=0xabc&tx_type=register_commitment",
        )
    assert res.status_code == 200
    assert res.json()["tx_hash"] == "0xabc"
    app.dependency_overrides.clear()


def test_transactions_wrong_state():
    commitment = MagicMock()
    commitment.commitment_id = "0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871"
    commitment.state = "prepared"

    def get_side_effect(model, id):
        if model is Commitment:
            return commitment
        return None

    session = MagicMock()
    session.get.side_effect = get_side_effect

    def override_db():
        yield session
    from backend.db import get_db
    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    res = client.post(
        "/api/v1/commitments/0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871/transactions?tx_hash=0xabc&tx_type=register_commitment",
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "INVALID_STATE"
    app.dependency_overrides.clear()


def test_transactions_chain_error():
    commitment = MagicMock()
    commitment.commitment_id = "0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871"
    commitment.state = "funded"
    commitment.parcel_id = "parcel_01"
    commitment.season_id = "season-2024"
    commitment.plan_hash = "0x705b7a9dd94979bbc79a1af1a17b5aed531a3a3e7b27cb5a5f15635e1a1ee127"

    def get_side_effect(model, id):
        if model is Commitment:
            return commitment
        return None

    session = MagicMock()
    session.get.side_effect = get_side_effect

    def override_db():
        yield session
    from backend.db import get_db
    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    with patch("backend.api.v1.transactions.verify_transaction") as mock_verify, \
         patch("backend.api.v1.transactions.create_web3") as mock_create_web3:
        mock_verify.side_effect = Exception("TX_MISMATCH")
        mock_create_web3.return_value = MagicMock()
        res = client.post(
            "/api/v1/commitments/0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871/transactions?tx_hash=0xabc&tx_type=register_commitment",
        )
    assert res.status_code == 502
    assert res.json()["detail"]["error"]["code"] == "CHAIN_SERVICE_ERROR"
    app.dependency_overrides.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])