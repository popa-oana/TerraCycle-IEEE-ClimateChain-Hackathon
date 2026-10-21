# -*- coding: utf-8 -*-
"""
tests/test_frontend_proof_contract.py — contract checks between the verified
proof document and the recovered React frontend (TASK-003D.2).

These tests need no browser and no JavaScript toolchain: they read the frontend
sources and compare them with the real document served by
scripts/serve_demo.py.

Covered:
- the frontend proof types match the real `demo-proof-v1` document
- the proof client validates every required field
- no evidence value is hardcoded in the frontend
- the Vite dev/preview server proxies /api/proof to the proof server
- the served document is the same one the frontend reads
"""
# -*- coding: utf-8 -*-
import json
import re
import sys
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"
PROOF_PATH = REPO_ROOT / "data" / "demo" / "latest_proof.json"

TYPES_SOURCE = FRONTEND / "src" / "lib" / "types.ts"
PROOF_CLIENT = FRONTEND / "src" / "lib" / "proof.ts"
PROOF_PAGE = FRONTEND / "src" / "pages" / "ProofPage.tsx"
APP_SOURCE = FRONTEND / "src" / "App.tsx"
VITE_CONFIG = FRONTEND / "vite.config.ts"

# The sections of the demo-proof-v1 document and the interface each one needs.
SECTION_FIELDS = {
    "run": ["status", "local_only", "network", "chain_id", "rpc_url"],
    "parcel": [
        "parcel_id",
        "season_id",
        "satellite_provider",
        "satellite_dataset",
        "satellite_method",
        "source_csv",
        "observations_total",
        "observations_valid",
        "source_rows",
    ],
    "verification": [
        "policy_version",
        "policy_type",
        "window_start",
        "window_end",
        "ndvi_threshold",
        "required_fraction",
        "min_observations",
        "verdict",
        "verdict_code",
        "reason_code",
        "reason",
        "evidence_quality",
        "temporal_coverage",
        "evidence_quality_warnings",
    ],
    "evidence": [
        "schema_version",
        "evidence_id",
        "commitment_id",
        "plan_id",
        "plan_hash",
        "evidence_hash",
        "evidence_hash_recomputed",
        "canonical_bytes_length",
    ],
    "blockchain": [
        "network",
        "chain_id",
        "registry_address",
        "deploy_tx_hash",
        "tx_hash",
        "receipt_status",
        "event",
        "on_chain",
    ],
}


def _document() -> dict:
    if not PROOF_PATH.exists():
        pytest.skip("no demonstration document on disk")
    return json.loads(PROOF_PATH.read_text(encoding="utf-8"))


def _types_interface(name: str) -> str:
    """Extract one TypeScript interface body from lib/types.ts."""
    source = TYPES_SOURCE.read_text(encoding="utf-8")
    match = re.search(rf"export interface {name} \{{(.*?)\n\}}", source, re.DOTALL)
    assert match, f"{name} is not declared in {TYPES_SOURCE}"
    return match.group(1)


class TestProofTypesMatchTheDocument:
    def test_document_has_the_expected_sections(self):
        document = _document()
        assert document["schema_version"] == "demo-proof-v1"
        for section in SECTION_FIELDS:
            assert section in document, f"the document has no {section} section"

    @pytest.mark.parametrize("section", sorted(SECTION_FIELDS))
    def test_every_document_field_is_declared_in_the_types(self, section):
        document = _document()
        body = _types_interface("Proof" + section.capitalize())
        declared = set(re.findall(r"^\s{2}(\w+)\??:", body, re.MULTILINE))
        for field in SECTION_FIELDS[section]:
            assert field in declared, f"{section}.{field} is not declared in the frontend types"

    def test_nested_event_and_on_chain_types_exist(self):
        document = _document()
        event = _types_interface("ProofEvent")
        on_chain = _types_interface("ProofOnChain")
        for field in SECTION_FIELDS["blockchain"]:
            if field in ("event", "on_chain"):
                continue
            assert field in document["blockchain"]
        for field in ["name", "commitment_id", "evidence_hash", "verdict_code", "recorder", "recorded_at"]:
            assert field in event
        for field in ["commitment_id", "evidence_hash", "verdict_code", "read_back_match"]:
            assert field in on_chain

    def test_proof_document_type_is_declared(self):
        body = _types_interface("ProofDocument")
        for field in ["schema_version", "generated_at", "run", "parcel", "verification", "evidence", "blockchain", "integrity", "limitations"]:
            assert field in body


class TestProofClient:
    def test_client_validates_the_required_sections(self):
        source = PROOF_CLIENT.read_text(encoding="utf-8")
        for section in SECTION_FIELDS:
            assert f"requireSection(payload, '{section}')" in source, section

    def test_client_validates_every_required_field(self):
        source = PROOF_CLIENT.read_text(encoding="utf-8")
        document = _document()
        for section, fields in SECTION_FIELDS.items():
            for field in fields:
                if section == "blockchain" and field in ("event", "on_chain"):
                    continue
                assert f"'{field}'" in source, f"{section}.{field} is not validated"

    def test_client_uses_the_shared_error_helpers(self):
        source = PROOF_CLIENT.read_text(encoding="utf-8")
        assert "readErrorPayload" in source
        assert "readJsonBody" in source
        assert "ApiError" in source

    def test_client_never_substitutes_placeholder_values(self):
        source = PROOF_CLIENT.read_text(encoding="utf-8")
        assert "INVALID_RESPONSE" in source
        assert "NETWORK_ERROR" in source
        # No fabricated evidence may be returned when the document is unusable.
        assert not re.search(r"0x[0-9a-fA-F]{40,64}", source)


class TestNoHardcodedEvidence:
    def test_frontend_sources_contain_no_evidence_values(self):
        for path in (PROOF_CLIENT, PROOF_PAGE, APP_SOURCE, TYPES_SOURCE):
            text = path.read_text(encoding="utf-8")
            assert not re.search(r"0x[0-9a-fA-F]{40,64}", text), f"{path} hardcodes a hash"
            assert "parcel_01" not in text, f"{path} hardcodes a parcel id"
            assert "nonconform" not in text.lower() or path == PROOF_PAGE, (
                f"{path} hardcodes a verdict"
            )

    def test_verdict_mapping_covers_every_terra_cycle_code(self):
        source = PROOF_PAGE.read_text(encoding="utf-8")
        for verdict in ("conform", "nonconform", "inconclusive"):
            assert f"{verdict}:" in source, f"the page cannot render the {verdict} verdict"


class TestProofServerWiring:
    def test_vite_proxies_the_proof_path(self):
        source = VITE_CONFIG.read_text(encoding="utf-8")
        assert "'/api/proof'" in source
        assert "PROOF_SERVER_ORIGIN" in source
        assert "preview" in source and "proxy" in source

    def test_served_document_matches_the_file_on_disk(self):
        """The proof server returns exactly the document the frontend validates."""
        import threading

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import serve_demo  # noqa: PLC0415 - imported after sys.path setup

        document = _document()
        server = serve_demo.create_server("127.0.0.1", 0, PROOF_PATH, quiet=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/api/proof"
            with urllib.request.urlopen(url, timeout=10) as response:
                assert response.status == 200
                served = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        assert served == document
