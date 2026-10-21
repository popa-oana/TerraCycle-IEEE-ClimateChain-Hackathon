# -*- coding: utf-8 -*-
"""
tests/test_frontend_parcel_contract.py — contract checks between the real
backend parcel response and the recovered React frontend (TASK-003D.3).

The frontend validator is executed for real: the test produces the genuine
`GET /api/v1/parcels` payload with the FastAPI TestClient and runs the
frontend's own `isParcel` from `frontend/src/lib/api.ts` in Node (type
stripping, no test framework). Node is optional: the test is skipped when it
is unavailable.
"""
# -*- coding: utf-8 -*-
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"
CHECK_SCRIPT = FRONTEND / "test" / "parcel-contract.check.mjs"
API_SOURCE = FRONTEND / "src" / "lib" / "api.ts"
TYPES_SOURCE = FRONTEND / "src" / "lib" / "types.ts"

NODE = shutil.which("node")


def _real_parcels_payload() -> dict:
    """The genuine response body of GET /api/v1/parcels."""
    from fastapi.testclient import TestClient

    from backend.main import app

    response = TestClient(app).get("/api/v1/parcels")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def parcels_payload() -> dict:
    return _real_parcels_payload()


class TestRealBackendPayload:
    def test_backend_serves_the_genuine_parcels(self, parcels_payload):
        parcels = parcels_payload["parcels"]
        assert len(parcels) == 3
        assert {p["parcel_id"] for p in parcels} == {"parcel_01", "parcel_02", "parcel_03"}
        assert all("display_name" in p and "area_ha" in p for p in parcels)

    def test_backend_does_not_publish_coordinates(self, parcels_payload):
        """This branch's parcels carry no position: none may be invented."""
        for parcel in parcels_payload["parcels"]:
            assert "latitude" not in parcel
            assert "longitude" not in parcel

    def test_frontend_declares_coordinates_as_optional(self):
        source = TYPES_SOURCE.read_text(encoding="utf-8")
        interface = source.split("export interface Parcel {", 1)[1].split("}", 1)[0]
        assert "latitude?: number;" in interface
        assert "longitude?: number;" in interface
        # Genuinely required fields stay required.
        for field in ("parcel_id: string;", "area_ha: number;", "geometry_url: string;"):
            assert field in interface

    def test_validator_keeps_coordinates_optional_but_checked(self):
        source = API_SOURCE.read_text(encoding="utf-8")
        assert "hasOptionalNumber(value.latitude)" in source
        assert "hasOptionalNumber(value.longitude)" in source
        # The parcel id and the other required fields are still validated.
        for check in ("value.parcel_id === 'string'", "value.area_ha === 'number'", "value.geometry_url === 'string'"):
            assert check in source

    def test_no_coordinate_fallback_is_invented(self):
        for path in (API_SOURCE, TYPES_SOURCE, FRONTEND / "src" / "pages" / "ParcelsPage.tsx"):
            text = path.read_text(encoding="utf-8")
            assert "?? 0" not in text, f"{path} invents a zero coordinate"
            assert "|| 0" not in text, f"{path} invents a zero coordinate"


@pytest.mark.skipif(NODE is None, reason="node is not available")
class TestFrontendValidatorAgainstTheRealPayload:
    def test_real_backend_response_is_accepted_by_the_frontend_client(self, parcels_payload, tmp_path):
        payload_file = tmp_path / "parcels.json"
        payload_file.write_text(json.dumps(parcels_payload), encoding="utf-8")

        result = subprocess.run(
            [NODE, "--experimental-strip-types", str(CHECK_SCRIPT), str(payload_file)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "all parcel contract checks passed" in result.stdout
