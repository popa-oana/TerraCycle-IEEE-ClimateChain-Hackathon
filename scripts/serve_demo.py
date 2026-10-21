#!/usr/bin/env python
"""
scripts/serve_demo.py — minimal read-only server for the TerraCycle demo page.

Serves exactly four things and nothing else:

    /            -> demo/index.html
    /styles.css  -> demo/styles.css
    /app.js      -> demo/app.js
    /api/proof   -> data/demo/latest_proof.json  (the verified demonstration)

It is NOT a generic file server: every other path returns 404, so the
repository (.env, .git, backend code, ML artefacts) is never exposed.

Standard library only. Binds to localhost by default.

Usage:
    python scripts/serve_demo.py                 # http://127.0.0.1:8090
    python scripts/serve_demo.py --port 8123
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "demo"
DEFAULT_PROOF_PATH = REPO_ROOT / "data" / "demo" / "latest_proof.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8090

# Explicit route table: only these paths exist.
STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}
PROOF_ROUTE = "/api/proof"


def make_handler(proof_path: Path, quiet: bool = False):
    """Build a request handler bound to one proof document."""

    class DemoHandler(BaseHTTPRequestHandler):
        server_version = "TerraCycleDemo/1.0"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # noqa: A003 - stdlib signature
            if not quiet:
                sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        # -- responses -------------------------------------------------

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _send_json(self, status: int, payload: dict) -> None:
            body = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        # -- routes ----------------------------------------------------

        def do_HEAD(self):  # noqa: N802 - stdlib naming
            self.do_GET()

        def do_GET(self):  # noqa: N802 - stdlib naming
            path = self.path.split("?", 1)[0].split("#", 1)[0]

            if path in STATIC_ROUTES:
                name, content_type = STATIC_ROUTES[path]
                asset = DEMO_DIR / name
                if not asset.is_file():
                    return self._send_json(
                        404,
                        {
                            "error": {
                                "code": "ASSET_MISSING",
                                "message": f"The demo asset '{name}' is missing from the repository.",
                            }
                        },
                    )
                return self._send(200, asset.read_bytes(), content_type)

            if path == PROOF_ROUTE:
                return self._serve_proof()

            return self._send_json(
                404,
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "This server exposes only the demo page and the demonstration document.",
                    }
                },
            )

        def _serve_proof(self) -> None:
            if not proof_path.is_file():
                return self._send_json(
                    503,
                    {
                        "error": {
                            "code": "PROOF_UNAVAILABLE",
                            "message": (
                                "No demonstration document found. Run the real-evidence "
                                "demonstration to generate it."
                            ),
                        }
                    },
                )
            raw = proof_path.read_bytes()
            try:
                json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                return self._send_json(
                    500,
                    {
                        "error": {
                            "code": "PROOF_MALFORMED",
                            "message": f"The demonstration document is not valid JSON: {exc}",
                        }
                    },
                )
            return self._send(200, raw, "application/json; charset=utf-8")

    return DemoHandler


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    proof_path: Path = DEFAULT_PROOF_PATH,
    quiet: bool = False,
) -> ThreadingHTTPServer:
    """Create (but do not start) the demo server."""
    handler = make_handler(Path(proof_path), quiet=quiet)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the read-only TerraCycle demo page.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to bind (default: 8090)")
    parser.add_argument(
        "--proof",
        default=str(DEFAULT_PROOF_PATH),
        help="path to the demonstration document (default: data/demo/latest_proof.json)",
    )
    parser.add_argument("--quiet", action="store_true", help="do not log requests")
    args = parser.parse_args()

    proof_path = Path(args.proof)
    if not proof_path.is_absolute():
        proof_path = Path.cwd() / proof_path

    server = create_server(args.host, args.port, proof_path, quiet=args.quiet)
    host, port = server.server_address[0], server.server_address[1]
    print(f"TerraCycle demo (read-only) on http://{host}:{port}")
    print(f"  demonstration document: {proof_path}")
    print("  press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
