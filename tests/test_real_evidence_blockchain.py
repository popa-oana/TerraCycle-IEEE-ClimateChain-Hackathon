# -*- coding: utf-8 -*-
"""
tests/test_real_evidence_blockchain.py — focused tests for the real-evidence
demonstration (TASK-002C).

Covered:
- the real Sentinel-2 verifier output is accepted by the canonical evidence builder
- the canonical evidence document contains no unsupported floats
- the evidence hash is reproducible for identical inputs
- the commitment id and verdict code are preserved exactly
- a nonconform or inconclusive verdict is never converted to conform
- missing satellite data fails safely
- a failed blockchain transaction fails the demonstration
- missing Anvil / Foundry dependencies are reported clearly
- with a local Anvil running: the real evidence is recorded and read back exactly

The chain test is skipped when no local Anvil is reachable; the demonstration
script `contracts/smoke_test_real_evidence.py` always performs a genuine
local transaction.
"""
# -*- coding: utf-8 -*-
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from web3 import Web3

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = REPO_ROOT / "contracts"
if str(CONTRACTS_DIR) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_DIR))

import smoke_test  # noqa: E402
import smoke_test_real_evidence as demo  # noqa: E402
from smoke_test import connect, load_bytecode, verify_recorded_evidence  # noqa: E402

from backend.hashing import canonical_bytes  # noqa: E402
from backend.ml.rules import verify_parcel  # noqa: E402

RPC_URL = os.environ.get("ANVIL_RPC_URL", "http://127.0.0.1:8545")
PRIVATE_KEY = os.environ.get("ANVIL_PRIVATE_KEY")


def _anvil_available() -> bool:
    try:
        return Web3(Web3.HTTPProvider(RPC_URL)).is_connected()
    except Exception:  # noqa: BLE001
        return False


requires_chain = pytest.mark.skipif(
    not (PRIVATE_KEY and _anvil_available()),
    reason="a local Anvil chain and ANVIL_PRIVATE_KEY are required",
)


def _contains_float(value) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_float(child) for child in value)
    return False


@pytest.fixture(scope="module")
def real_evidence():
    """Generate the genuine evidence of parcel_01 once for the whole module."""
    return demo.generate_real_evidence()


class TestRealEvidenceGeneration:
    def test_evidence_comes_from_the_real_sentinel2_export(self, real_evidence):
        source = real_evidence["verifier_result"]["source"]
        assert source["provider"] == "Copernicus Data Space"
        assert source["dataset"] == "Sentinel-2 L2A"
        assert source["csv_file"].endswith("parcel_01_2024_quality.csv")
        assert Path(source["csv_file"]).exists()

    def test_verifier_output_is_accepted_by_the_evidence_builder(self, real_evidence):
        doc = real_evidence["evidence_doc"]
        assert doc["schema_version"] == "evidence-v1"
        assert doc["commitment_id"] == real_evidence["commitment_id"]
        assert doc["plan_hash"] == real_evidence["plan_hash"]
        assert doc["observations"], "the canonical document must carry the real observations"
        assert doc["quality"]["total_rows"] > 0
        assert doc["policy"]["policy_version"] == "cover-v1"

    def test_canonical_evidence_contains_no_floats(self, real_evidence):
        doc = real_evidence["evidence_doc"]
        assert not _contains_float(doc)
        assert canonical_bytes(doc) == real_evidence["evidence_bytes"]

    def test_evidence_hash_is_reproducible_for_identical_inputs(self):
        first = demo.generate_real_evidence()
        second = demo.generate_real_evidence()
        assert first["evidence_bytes"] == second["evidence_bytes"]
        assert first["evidence_hash"] == second["evidence_hash"]
        assert first["evidence_hash"] == "0x" + hashlib.sha256(first["evidence_bytes"]).hexdigest()

    def test_commitment_id_comes_from_the_authoritative_preparation(self, real_evidence):
        fixture = json.loads(
            (REPO_ROOT / "data" / "fixtures" / "demo.json").read_text(encoding="utf-8")
        )
        assert real_evidence["commitment_id"] == fixture["reference_parcel"]["commitment_id"]
        assert real_evidence["commitment_id"] == real_evidence["commitment"].commitment_id
        assert real_evidence["commitment"].plan_hash == real_evidence["plan_hash"]

    def test_verdict_code_is_preserved(self, real_evidence):
        assert real_evidence["verdict_code"] == real_evidence["verifier_result"]["verdict_code"]
        assert real_evidence["evidence_doc"]["verdict_code"] == real_evidence["verdict_code"]
        assert real_evidence["verdict_code"] in (0, 1, 2)

    def test_nonconform_is_not_converted_to_conform(self, real_evidence):
        """The real parcel_01 result is nonconform and must stay nonconform."""
        assert real_evidence["verdict"] == "nonconform"
        assert real_evidence["verdict_code"] == 1
        assert real_evidence["verdict_code"] != 0
        assert real_evidence["evidence_doc"]["verdict"] == "nonconform"

    def test_inconclusive_is_not_converted_to_conform(self):
        """An empty commitment window stays inconclusive."""
        policy = dict(demo.load_policy("cover-v1"))
        policy["window_start"] = "2025-01-01"
        policy["window_end"] = "2025-02-01"
        result = verify_parcel("parcel_01", policy, str(demo.EVIDENCE_DIR))
        assert result["verdict"] == "inconclusive"
        assert result["verdict_code"] == 2
        assert result["verdict_code"] != 0

    def test_missing_satellite_data_fails_safely(self, tmp_path):
        """A parcel without NDVI data yields inconclusive, never conform."""
        result = verify_parcel("parcel_99", demo.load_policy("cover-v1"), str(tmp_path))
        assert result["verdict"] == "inconclusive"
        assert result["verdict_code"] == 2
        assert result["reason_code"] == "MISSING_EVIDENCE"


class TestDemonstrationFailureModes:
    def test_failed_blockchain_transaction_fails_the_demonstration(self):
        """A receipt with status 0 must abort the demonstration."""
        registry = Mock()
        registry.address = "0x" + "11" * 20
        receipt = {"status": 0, "to": registry.address, "logs": []}

        with pytest.raises(AssertionError):
            verify_recorded_evidence(
                registry,
                receipt,
                "0x" + "22" * 32,
                "0x" + "33" * 32,
                1,
                "0x" + "44" * 20,
            )

    def test_missing_anvil_is_reported_clearly(self):
        """An unreachable local chain produces a clear error, not a silent pass."""
        with pytest.raises(SystemExit):
            connect("http://127.0.0.1:9")

    def test_missing_foundry_artifact_is_reported_clearly(self, tmp_path, monkeypatch):
        """A missing forge build artifact produces a clear error."""
        monkeypatch.setattr(smoke_test, "ARTIFACT_PATH", tmp_path / "missing.json")
        with pytest.raises(SystemExit):
            load_bytecode()


class TestLocalChainRoundTrip:
    @requires_chain
    def test_real_evidence_is_recorded_and_read_back_exactly(self, real_evidence):
        """A genuine local transaction stores exactly the generated evidence."""
        w3 = connect(RPC_URL)
        abi = smoke_test.load_abi()
        deployer = w3.eth.account.from_key(PRIVATE_KEY).address

        registry_address, _ = smoke_test.deploy_registry(
            w3, abi, load_bytecode(), deployer, deployer, PRIVATE_KEY
        )
        registry = w3.eth.contract(address=registry_address, abi=abi)

        receipt = smoke_test.record_evidence(
            w3,
            registry,
            real_evidence["commitment_id"],
            real_evidence["evidence_hash"],
            real_evidence["verdict_code"],
            deployer,
            PRIVATE_KEY,
        )
        verify_recorded_evidence(
            registry,
            receipt,
            real_evidence["commitment_id"],
            real_evidence["evidence_hash"],
            real_evidence["verdict_code"],
            deployer,
        )

        stored = registry.functions.getEvidence(real_evidence["commitment_id"]).call()
        assert smoke_test.to_hex(stored[0]) == real_evidence["commitment_id"]
        assert smoke_test.to_hex(stored[1]) == real_evidence["evidence_hash"]
        assert stored[2] == real_evidence["verdict_code"]
        assert (
            "0x" + hashlib.sha256(real_evidence["evidence_bytes"]).hexdigest()
            == real_evidence["evidence_hash"]
        )
