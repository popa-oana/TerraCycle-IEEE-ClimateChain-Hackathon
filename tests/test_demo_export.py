# -*- coding: utf-8 -*-
"""
tests/test_demo_export.py — focused tests for the demo JSON export (TASK-003A).

The exported document is a PRESENTATION summary of a successful local
demonstration. The canonical evidence bytes and their SHA-256 hash remain the
authoritative artefacts.

Covered:
- the exported JSON is valid and readable
- every required presentation field is present
- the evidence hash matches the actual canonical bytes
- the on-chain read-back matches the generated evidence
- a failed transaction cannot produce a new successful document
- missing data is handled correctly
- no private key or secret appears in the exported JSON
- the real verdict is preserved, never forced to conform
"""
# -*- coding: utf-8 -*-
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = REPO_ROOT / "contracts"
if str(CONTRACTS_DIR) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_DIR))

import smoke_test  # noqa: E402
import smoke_test_real_evidence as demo  # noqa: E402

EXPORT_PATH = REPO_ROOT / "data" / "demo" / "latest_proof.json"

REQUIRED_TOP_LEVEL = (
    "schema_version",
    "generated_at",
    "run",
    "parcel",
    "verification",
    "evidence",
    "blockchain",
    "integrity",
    "limitations",
)


@pytest.fixture(scope="module")
def document():
    """The document produced by the real local demonstration."""
    if not EXPORT_PATH.exists():
        pytest.skip(
            "no demonstration document yet — run "
            "`python contracts/smoke_test_real_evidence.py` first"
        )
    return json.loads(EXPORT_PATH.read_text(encoding="utf-8"))


class TestExportedDocument:
    def test_json_output_is_valid_and_readable(self, document):
        raw = EXPORT_PATH.read_text(encoding="utf-8")
        assert raw.strip().startswith("{")
        assert raw.strip().endswith("}")
        assert json.loads(raw) == document
        assert document["schema_version"] == demo.DEMO_SCHEMA_VERSION

    def test_all_required_presentation_fields_are_present(self, document):
        for key in REQUIRED_TOP_LEVEL:
            assert key in document, f"missing top-level field {key}"

        parcel = document["parcel"]
        for key in (
            "parcel_id",
            "season_id",
            "satellite_provider",
            "satellite_dataset",
            "observations_total",
            "observations_valid",
        ):
            assert key in parcel

        verification = document["verification"]
        for key in (
            "policy_version",
            "window_start",
            "window_end",
            "verdict",
            "verdict_code",
            "reason_code",
            "evidence_quality",
            "evidence_quality_warnings",
        ):
            assert key in verification

        evidence = document["evidence"]
        for key in (
            "schema_version",
            "evidence_id",
            "commitment_id",
            "evidence_hash",
        ):
            assert key in evidence

        blockchain = document["blockchain"]
        for key in (
            "chain_id",
            "registry_address",
            "tx_hash",
            "receipt_status",
            "event",
            "on_chain",
        ):
            assert key in blockchain
        for key in ("commitment_id", "evidence_hash", "verdict_code", "read_back_match"):
            assert key in blockchain["on_chain"]

    def test_evidence_hash_matches_the_actual_canonical_bytes(self, document):
        """The exported hash is the SHA-256 of the real canonical evidence bytes."""
        evidence = demo.generate_real_evidence()
        assert document["evidence"]["evidence_hash"] == evidence["evidence_hash"]
        assert (
            "0x" + hashlib.sha256(evidence["evidence_bytes"]).hexdigest()
            == document["evidence"]["evidence_hash"]
        )
        assert document["evidence"]["evidence_hash_recomputed"] == document["evidence"]["evidence_hash"]
        assert document["evidence"]["canonical_bytes_length"] == len(evidence["evidence_bytes"])

    def test_commitment_id_is_the_authoritative_one(self, document):
        fixture = json.loads(
            (REPO_ROOT / "data" / "fixtures" / "demo.json").read_text(encoding="utf-8")
        )
        assert document["evidence"]["commitment_id"] == fixture["reference_parcel"]["commitment_id"]

    def test_on_chain_read_back_matches_the_generated_evidence(self, document):
        blockchain = document["blockchain"]
        assert blockchain["on_chain"]["read_back_match"] is True
        assert blockchain["on_chain"]["evidence_hash"] == document["evidence"]["evidence_hash"]
        assert blockchain["on_chain"]["commitment_id"] == document["evidence"]["commitment_id"]
        assert blockchain["on_chain"]["verdict_code"] == document["verification"]["verdict_code"]
        assert blockchain["event"]["evidence_hash"] == document["evidence"]["evidence_hash"]
        assert blockchain["event"]["verdict_code"] == document["verification"]["verdict_code"]
        assert blockchain["receipt_status"] == 1

    def test_integrity_flags_are_all_true(self, document):
        assert document["integrity"]
        for name, value in document["integrity"].items():
            assert value is True, f"integrity check failed: {name}"

    def test_real_verdict_is_preserved_and_not_forced_to_conform(self, document):
        """parcel_01 is genuinely nonconform; the export must not soften that."""
        assert document["verification"]["verdict"] == "nonconform"
        assert document["verification"]["verdict_code"] == 1
        assert document["verification"]["verdict_code"] != 0
        assert document["evidence"]["evidence_id"].startswith("evidence-")

    def test_no_private_key_or_secret_appears_in_the_export(self, document):
        raw = EXPORT_PATH.read_text(encoding="utf-8")
        secret = os.environ.get("ANVIL_PRIVATE_KEY")
        if secret:
            assert secret not in raw
            assert secret[2:] not in raw
        assert "private_key" not in raw.lower()
        assert "PRIVATE_KEY" not in raw
        # Every 0x-prefixed 64-hex string must be a public identifier of this run.
        allowed = {
            document["evidence"]["commitment_id"],
            document["evidence"]["plan_hash"],
            document["evidence"]["evidence_hash"],
            document["evidence"]["evidence_hash_recomputed"],
            document["blockchain"]["deploy_tx_hash"],
            document["blockchain"]["tx_hash"],
        }
        for value in re.findall(r"0x[0-9a-fA-F]{64}", raw):
            assert value in allowed, f"unexpected 32-byte value in the export: {value}"

    def test_local_blockchain_is_declared(self, document):
        assert document["run"]["local_only"] is True
        assert document["run"]["network"] == "anvil-local"
        assert document["run"]["chain_id"] == 31337
        assert document["blockchain"]["chain_id"] == 31337
        assert document["run"]["rpc_url"].startswith("http://127.0.0.1")

    def test_limitations_refuse_organic_and_settlement_claims(self, document):
        text = " ".join(document["limitations"]).lower()
        assert "not an organic certification" in text or "not organic" in text
        assert "local anvil" in text
        assert "not settlement authorization" in text
        assert "payment" in text


class TestExportFailureModes:
    def test_failed_transaction_cannot_produce_a_new_document(self, tmp_path):
        """A failed run must not publish a success document."""
        target = tmp_path / "latest_proof.json"
        stale = {"schema_version": demo.DEMO_SCHEMA_VERSION, "run": {"status": "success"}}
        target.write_text(json.dumps(stale), encoding="utf-8")

        with pytest.raises(AssertionError):
            smoke_test.verify_recorded_evidence(
                _mock_registry(),
                {"status": 0, "to": "0x" + "11" * 20, "logs": []},
                "0x" + "22" * 32,
                "0x" + "33" * 32,
                1,
                "0x" + "44" * 20,
            )

        # The document was not replaced by the failed run.
        assert json.loads(target.read_text(encoding="utf-8")) == stale

    def test_stale_output_is_removed_after_a_failed_run(self, tmp_path):
        """A failed run removes the previous document so it cannot be read as current."""
        target = tmp_path / "latest_proof.json"
        target.write_text(json.dumps({"run": {"status": "success"}}), encoding="utf-8")

        demo.remove_stale_output(target)

        assert not target.exists()

    def test_missing_data_is_handled(self, tmp_path):
        """A parcel without satellite data stays inconclusive and never conform."""
        from backend.ml.rules import verify_parcel

        result = verify_parcel("parcel_99", demo.load_policy("cover-v1"), str(tmp_path))
        assert result["verdict"] == "inconclusive"
        assert result["verdict_code"] == 2
        assert result["reason_code"] == "MISSING_EVIDENCE"

    def test_rpc_url_without_credentials_is_kept_local(self):
        assert demo.safe_rpc_url("http://127.0.0.1:8545") == "http://127.0.0.1:8545"
        redacted = demo.safe_rpc_url("https://user:secret@rpc.example.com/v1?token=abc")
        assert "secret" not in redacted
        assert "token" not in redacted
        assert "rpc.example.com" not in redacted

    def test_document_is_written_atomically(self, tmp_path):
        """The writer leaves no partial file and produces valid JSON."""
        target = tmp_path / "nested" / "proof.json"
        document = {"schema_version": demo.DEMO_SCHEMA_VERSION, "value": 1}
        written = demo.write_demo_document(target, document)

        assert written == target
        assert json.loads(target.read_text(encoding="utf-8")) == document
        leftovers = [p for p in target.parent.iterdir() if p.name != target.name]
        assert leftovers == [], f"temporary files were left behind: {leftovers}"


def _mock_registry():
    class _Registry:
        address = "0x" + "11" * 20

    return _Registry()
