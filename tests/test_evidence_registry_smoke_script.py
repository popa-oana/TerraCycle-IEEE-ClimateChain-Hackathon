# -*- coding: utf-8 -*-
"""
tests/test_evidence_registry_smoke_script.py — consistency guards for the
local blockchain smoke test of the TerraCycle evidence registry.

These checks need no running chain: they make sure the committed ABI, the
Solidity source and the Python smoke script still agree with each other.

The real chain interaction is verified by `contracts/smoke_test.py`, which must
be run against a live local Anvil node.
"""
# -*- coding: utf-8 -*-
import json
import py_compile
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = REPO_ROOT / "contracts"

ABI_PATH = CONTRACTS_DIR / "abi" / "TerraCycleEvidenceRegistry.json"
CONTRACT_PATH = CONTRACTS_DIR / "src" / "TerraCycleEvidenceRegistry.sol"
SCRIPT_PATH = CONTRACTS_DIR / "smoke_test.py"


def _abi() -> list:
    return json.loads(ABI_PATH.read_text(encoding="utf-8"))


def _script_source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


class TestCommittedAbi:
    def test_abi_exposes_the_registry_interface(self):
        """The published ABI still matches the implemented contract."""
        entries = _abi()
        functions = {e["name"] for e in entries if e["type"] == "function"}
        events = {e["name"] for e in entries if e["type"] == "event"}
        errors = {e["name"] for e in entries if e["type"] == "error"}

        assert {
            "recordEvidence",
            "getEvidence",
            "hasEvidence",
            "verifier",
            "VERDICT_CONFORM",
            "VERDICT_NONCONFORM",
            "VERDICT_INCONCLUSIVE",
        } <= functions
        assert "EvidenceRecorded" in events
        assert {
            "NotVerifier",
            "ZeroVerifierAddress",
            "ZeroCommitmentId",
            "ZeroEvidenceHash",
            "InvalidVerdict",
            "EvidenceAlreadyRecorded",
        } <= errors

    def test_record_evidence_signature_is_stable(self):
        """recordEvidence(bytes32,bytes32,uint8) must not drift."""
        record = next(
            e for e in _abi() if e.get("type") == "function" and e["name"] == "recordEvidence"
        )
        assert [i["type"] for i in record["inputs"]] == ["bytes32", "bytes32", "uint8"]
        assert record["stateMutability"] == "nonpayable"

    def test_constructor_takes_the_verifier_address(self):
        constructor = next(e for e in _abi() if e["type"] == "constructor")
        assert [i["type"] for i in constructor["inputs"]] == ["address"]
        assert constructor["stateMutability"] == "nonpayable"


class TestContractSource:
    def test_contract_declares_the_expected_verdict_codes(self):
        source = CONTRACT_PATH.read_text(encoding="utf-8")
        assert "VERDICT_CONFORM = 0" in source
        assert "VERDICT_NONCONFORM = 1" in source
        assert "VERDICT_INCONCLUSIVE = 2" in source

    def test_contract_has_no_payable_or_transfer_surface(self):
        """The registry must not receive ETH and must not move funds."""
        source = CONTRACT_PATH.read_text(encoding="utf-8")
        assert "payable" not in source
        assert ".transfer(" not in source
        assert ".send(" not in source
        assert ".call{value" not in source


class TestSmokeScript:
    def test_script_is_valid_python(self, tmp_path):
        py_compile.compile(str(SCRIPT_PATH), cfile=str(tmp_path / "smoke_test.pyc"), doraise=True)

    def test_script_uses_deterministic_test_values(self):
        source = _script_source()
        commitment = re.search(r'TEST_COMMITMENT_ID = "0x" \+ "74657374" \+ "0" \* (\d+) \+ "01"', source)
        evidence = re.search(r'TEST_EVIDENCE_HASH = "0x" \+ "74657374" \+ "0" \* (\d+) \+ "02"', source)
        assert commitment and evidence
        # "74657374" (8 hex chars) + zeros + 2 hex chars must be 32 bytes.
        assert 8 + int(commitment.group(1)) + 2 == 64
        assert 8 + int(evidence.group(1)) + 2 == 64

    def test_script_targets_the_documented_local_chain(self):
        source = _script_source()
        assert "EXPECTED_CHAIN_ID = 31337" in source
        assert "http://127.0.0.1:8545" in source

    def test_script_requires_a_private_key_from_the_environment(self):
        """No private key may be hardcoded in the committed script."""
        source = _script_source()
        assert "ANVIL_PRIVATE_KEY" in source
        assert not re.search(r"0x[0-9a-fA-F]{64}", source)

    def test_script_exits_non_zero_on_failure(self):
        source = _script_source()
        assert "sys.exit(1)" in source
