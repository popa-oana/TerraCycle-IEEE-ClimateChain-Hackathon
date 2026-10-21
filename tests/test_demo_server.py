# -*- coding: utf-8 -*-
"""
tests/test_demo_server.py — focused tests for the read-only demo interface.

Covered:
- the demo server starts and binds localhost
- the page is reachable and served as HTML
- the actual demonstration JSON can be retrieved
- the server exposes nothing else from the repository
- a missing document produces an error, not fake successful results
- a malformed document is handled safely
- the page hardcodes no evidence values
- the interface serves the current document

Every test starts its own server on an ephemeral localhost port; no external
service is contacted.
"""
# -*- coding: utf-8 -*-
import contextlib
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "demo"
PROOF_PATH = REPO_ROOT / "data" / "demo" / "latest_proof.json"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import serve_demo  # noqa: E402


@contextlib.contextmanager
def running_server(proof_path=PROOF_PATH):
    """Start the demo server on an ephemeral localhost port."""
    server = serve_demo.create_server("127.0.0.1", 0, Path(proof_path), quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def fetch(url):
    """Return (status, content_type, body_bytes) without raising on 4xx/5xx."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()


def read_assets():
    return {
        name: (DEMO_DIR / name).read_text(encoding="utf-8")
        for name in ("index.html", "app.js", "styles.css")
    }


class TestServerStarts:
    def test_server_starts_on_localhost(self):
        with running_server() as base_url:
            assert base_url.startswith("http://127.0.0.1:")
            status, _, _ = fetch(base_url + "/")
            assert status == 200

    def test_page_is_served_as_html(self):
        with running_server() as base_url:
            status, content_type, body = fetch(base_url + "/")
            assert status == 200
            assert "text/html" in content_type
            text = body.decode("utf-8")
            assert "TerraCycle Proof" in text
            assert "Satellite-backed environmental evidence verification" in text
            assert "Local Blockchain Demonstration" in text

    def test_static_assets_are_served(self):
        with running_server() as base_url:
            for path, expected in (("/app.js", "javascript"), ("/styles.css", "text/css")):
                status, content_type, body = fetch(base_url + path)
                assert status == 200, path
                assert expected in content_type, path
                assert body


class TestDocumentEndpoint:
    def test_actual_json_can_be_retrieved(self):
        with running_server() as base_url:
            status, content_type, body = fetch(base_url + "/api/proof")
            assert status == 200
            assert "application/json" in content_type
            document = json.loads(body.decode("utf-8"))
            assert document["schema_version"] == "demo-proof-v1"
            assert document["verification"]["verdict"]
            assert document["evidence"]["evidence_hash"]

    def test_served_document_is_the_current_file(self):
        """The interface serves the document that is on disk right now."""
        if not PROOF_PATH.exists():
            pytest.skip("no demonstration document on disk")
        with running_server() as base_url:
            _, _, body = fetch(base_url + "/api/proof")
            served = json.loads(body.decode("utf-8"))
            current = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
            assert served == current
            assert served["parcel"]["parcel_id"] == current["parcel"]["parcel_id"]
            assert served["verification"]["verdict_code"] == current["verification"]["verdict_code"]
            assert served["evidence"]["evidence_hash"] == current["evidence"]["evidence_hash"]

    def test_head_request_is_supported(self):
        with running_server() as base_url:
            status, _, _ = fetch(base_url + "/api/proof")
            assert status == 200


class TestNoRepositoryExposure:
    UNRELATED = (
        "/.env",
        "/.git/config",
        "/backend/api/v1/commitments.py",
        "/contracts/src/TerraCycleEvidenceRegistry.sol",
        "/data/demo/latest_proof.json",
        "/data/ndvi/parcel_01_2024_quality.csv",
        "/README.md",
        "/audit.md",
        "/tests/test_demo_server.py",
    )

    def test_unrelated_repository_files_are_not_exposed(self):
        with running_server() as base_url:
            for path in self.UNRELATED:
                status, _, body = fetch(base_url + path)
                assert status == 404, f"{path} returned {status}"
                assert b"PRIVATE_KEY" not in body
                assert b"DATABASE_URL" not in body

    def test_path_traversal_is_rejected(self):
        with running_server() as base_url:
            for path in ("/../.env", "/app.js/../../.env", "//../backend/db.py"):
                status, _, _ = fetch(base_url + path)
                assert status == 404, path

    def test_only_the_documented_routes_exist(self):
        with running_server() as base_url:
            for path in ("/", "/styles.css", "/app.js", "/api/proof"):
                status, _, _ = fetch(base_url + path)
                assert status == 200, path


class TestFailureStates:
    def test_missing_document_returns_an_error_not_fake_results(self, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        with running_server(missing) as base_url:
            status, content_type, body = fetch(base_url + "/api/proof")
            assert status == 503
            assert "application/json" in content_type
            payload = json.loads(body.decode("utf-8"))
            assert payload["error"]["code"] == "PROOF_UNAVAILABLE"
            # No fabricated successful-looking result.
            assert "verdict" not in payload
            assert "parcel_id" not in payload
            assert "evidence_hash" not in payload

    def test_malformed_document_is_handled_safely(self, tmp_path):
        broken = tmp_path / "broken.json"
        broken.write_text("{ this is not json", encoding="utf-8")
        with running_server(broken) as base_url:
            status, _, body = fetch(base_url + "/api/proof")
            assert status == 500
            payload = json.loads(body.decode("utf-8"))
            assert payload["error"]["code"] == "PROOF_MALFORMED"

            # The page itself still loads and can show the error state.
            page_status, _, page = fetch(base_url + "/")
            assert page_status == 200
            assert b'id="error-panel"' in page


class TestNoHardcodedEvidence:
    def test_assets_contain_no_evidence_values(self):
        for name, text in read_assets().items():
            assert not re.search(r"0x[0-9a-fA-F]{64}", text), f"{name} contains a 32-byte value"
            assert not re.search(r"0x[0-9a-fA-F]{40}", text), f"{name} contains an address"
            assert "parcel_01" not in text, f"{name} hardcodes a parcel id"

    def test_assets_do_not_contain_the_current_document_values(self):
        if not PROOF_PATH.exists():
            pytest.skip("no demonstration document on disk")
        document = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
        values = [
            document["evidence"]["evidence_hash"],
            document["evidence"]["commitment_id"],
            document["blockchain"]["tx_hash"],
            document["blockchain"]["registry_address"],
        ]
        for name, text in read_assets().items():
            for value in values:
                assert value not in text, f"{name} hardcodes {value}"

    def test_assets_fetch_the_document_from_the_server(self):
        sources = read_assets()
        assert "/api/proof" in sources["app.js"]
        assert "fetch(" in sources["app.js"]
        assert "/styles.css" in sources["index.html"]
        assert "/app.js" in sources["index.html"]

    def test_page_contains_every_required_section(self):
        html = (DEMO_DIR / "index.html").read_text(encoding="utf-8")
        for anchor in (
            "h-parcel",
            "h-verification",
            "h-evidence",
            "h-chain",
            "h-limitations",
            "h-integrity",
        ):
            assert f'id="{anchor}"' in html, f"missing section {anchor}"
        assert "Local Blockchain Demonstration" in html
        assert "not a public testnet" in html.lower()

    def test_page_states_the_required_limitations(self):
        html = (DEMO_DIR / "index.html").read_text(encoding="utf-8")
        text = html.lower()
        assert "organic certification" in text
        assert "anvil" in text
        assert "no automatic escrow settlement" in text or "escrow settlement" in text
