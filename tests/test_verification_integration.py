"""
tests/test_verification_integration.py — Day 6A integration tests

Tests the verify_parcel() entry point for all four real parcel IDs,
correct file selection, invalid inputs, JSON serialization, schema
compatibility, no cross-parcel contamination, commitment-window
enforcement, evidence warnings, and deterministic verification.

All tests use synthetic data in temporary directories. No real data
file is modified by these tests.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.rules import VERDICT_CODES, verify_parcel  # noqa: E402

STANDARD_COLUMNS = ["parcel_id", "acquired_at", "scene_id", "ndvi_mean", "valid_pixel_fraction"]

ALL_PARCELS = ("parcel_01", "parcel_02", "parcel_03", "parcel_04")

POLICY = {
    "window_start": "2024-03-01",
    "window_end": "2024-11-01",
    "ndvi_threshold": 0.35,
    "required_fraction": 0.80,
    "min_observations": 5,
    "min_valid_pixel_fraction": 0.50,
    "min_temporal_coverage": 0.50,
    "temporal_coverage_interval_days": 10,
}

# Dates spread across the full 2024-03-01..2024-11-01 window so that
# temporal coverage (Rule B) is satisfied: 15 distinct 10-day intervals
# covered out of 25 total => coverage 0.60 >= 0.50.
SEASON_DATES = [
    "2024-03-05", "2024-03-21", "2024-04-06", "2024-04-22",
    "2024-05-08", "2024-05-24", "2024-06-09", "2024-06-25",
    "2024-07-11", "2024-07-27", "2024-08-12", "2024-08-28",
    "2024-09-13", "2024-09-29", "2024-10-15",
]


def _high_ndvi_rows(parcel_id):
    """Generate rows with high NDVI spread across the full season."""
    return [
        (parcel_id, f"{d}T00:00:00Z", "", 0.6, 1.0)
        for d in SEASON_DATES
    ]


def _write_quality_csv(directory, parcel_id, rows):
    """Write a standard-schema quality CSV for one parcel."""
    path = directory / f"{parcel_id}_2024_quality.csv"
    with open(path, "w", encoding="utf-8") as f:
        f.write(",".join(STANDARD_COLUMNS) + "\n")
        for row in rows:
            f.write(",".join(str(v) for v in row) + "\n")
    return path


# ============================================================
# All four parcel identifiers
# ============================================================

class TestAllFourParcelIDs:
    """verify_parcel() must work for each of the four known parcels."""

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_valid_parcel_id(self, parcel_id, tmp_path):
        rows = _high_ndvi_rows(parcel_id)
        _write_quality_csv(tmp_path, parcel_id, rows)
        result = verify_parcel(parcel_id, POLICY, str(tmp_path))
        assert result["verdict"] == "conform"
        assert result["verdict_code"] == 0

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_invalid_parcel_id_returns_inconclusive(self, parcel_id, tmp_path):
        """A parcel ID with no CSV returns inconclusive, never fabricates data."""
        result = verify_parcel(parcel_id, POLICY, str(tmp_path))
        assert result["verdict"] == "inconclusive"
        assert result["verdict_code"] == 2
        assert result["reason_code"] == "MISSING_EVIDENCE"


# ============================================================
# Correct file selection
# ============================================================

class TestFileSelection:
    def test_selects_quality_csv_over_ndvi_only(self, tmp_path):
        """The quality CSV is preferred when both exist."""
        # NDVI-only CSV with low values
        ndvi_path = tmp_path / "parcel_01_2024.csv"
        with open(ndvi_path, "w", encoding="utf-8") as f:
            f.write("date,ndvi_mean\n")
            f.write("2024-04-01T00:00:00Z,0.1\n")
            f.write("2024-04-05T00:00:00Z,0.15\n")
            f.write("2024-04-10T00:00:00Z,0.12\n")
            f.write("2024-04-15T00:00:00Z,0.2\n")
            f.write("2024-04-20T00:00:00Z,0.18\n")

        # Quality CSV with high values spread across the season
        rows = _high_ndvi_rows("parcel_01")
        _write_quality_csv(tmp_path, "parcel_01", rows)

        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        # Quality CSV wins -- high NDVI => conform
        assert result["verdict"] == "conform"
        assert "quality" in result["source"]["csv_file"]

    def test_no_cross_parcel_contamination(self, tmp_path):
        """Each parcel loads only its own CSV."""
        for pid in ALL_PARCELS:
            rows = _high_ndvi_rows(pid)
            _write_quality_csv(tmp_path, pid, rows)

        for pid in ALL_PARCELS:
            result = verify_parcel(pid, POLICY, str(tmp_path))
            assert result["verdict"] == "conform"
            assert result["observations"]
            for obs in result["observations"]:
                assert isinstance(obs["acquired_at"], str)
                assert isinstance(obs["ndvi_mean"], float)


# ============================================================
# Missing input file
# ============================================================

class TestMissingInput:
    def test_missing_directory_returns_inconclusive(self):
        result = verify_parcel("parcel_01", POLICY, "/nonexistent/path")
        assert result["verdict"] == "inconclusive"
        assert result["reason_code"] == "MISSING_EVIDENCE"

    def test_empty_directory_returns_inconclusive(self, tmp_path):
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert result["verdict"] == "inconclusive"
        assert result["reason_code"] == "MISSING_EVIDENCE"


# ============================================================
# Malformed input
# ============================================================

class TestMalformedInput:
    def test_csv_with_wrong_columns(self, tmp_path):
        path = tmp_path / "parcel_01_2024.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("wrong1,wrong2\n")
            f.write("val1,val2\n")
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert result["verdict"] == "inconclusive"
        assert result["reason_code"] == "INVALID_CSV_STRUCTURE"

    def test_csv_with_no_data_rows(self, tmp_path):
        path = tmp_path / "parcel_01_2024.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("date,ndvi_mean\n")
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert result["verdict"] == "inconclusive"

    def test_csv_with_unparseable_dates(self, tmp_path):
        path = tmp_path / "parcel_01_2024.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("date,ndvi_mean\n")
            f.write("not-a-date,0.5\n")
            f.write("2024-04-01T00:00:00Z,0.6\n")
            f.write("2024-04-05T00:00:00Z,0.7\n")
            f.write("2024-04-10T00:00:00Z,0.65\n")
            f.write("2024-04-15T00:00:00Z,0.55\n")
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        # Only 4 valid rows (1 dropped) => inconclusive
        assert result["verdict"] == "inconclusive"
        assert result["quality"]["structural_excluded_count"] == 1


# ============================================================
# JSON serialization
# ============================================================

class TestJSONSerialization:
    def test_output_is_json_serializable(self, tmp_path):
        rows = _high_ndvi_rows("parcel_01")
        _write_quality_csv(tmp_path, "parcel_01", rows)
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))

        # Must not raise
        json_str = json.dumps(result, ensure_ascii=False)
        assert len(json_str) > 0

        # Must round-trip
        parsed = json.loads(json_str)
        assert parsed["verdict"] == result["verdict"]
        assert parsed["verdict_code"] == result["verdict_code"]


# ============================================================
# Response schema compatibility
# ============================================================

class TestResponseSchema:
    EXPECTED_TOP_LEVEL_KEYS = {
        "verdict", "verdict_code", "reason_code", "reason",
        "observations", "quality", "model", "source",
    }
    EXPECTED_QUALITY_KEYS = {
        "valid_count", "total_rows", "excluded_count",
        "quality_excluded_count", "vegetated_count", "vegetated_fraction",
        "quality_metadata_available", "evidence_quality",
        "temporal_coverage", "covered_intervals", "total_intervals",
        "interval_length_days", "warnings",
    }

    def test_top_level_keys_present(self, tmp_path):
        rows = _high_ndvi_rows("parcel_01")
        _write_quality_csv(tmp_path, "parcel_01", rows)
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert self.EXPECTED_TOP_LEVEL_KEYS.issubset(result.keys())

    def test_quality_keys_present(self, tmp_path):
        rows = _high_ndvi_rows("parcel_01")
        _write_quality_csv(tmp_path, "parcel_01", rows)
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert self.EXPECTED_QUALITY_KEYS.issubset(result["quality"].keys())

    def test_verdict_code_matches_verdict(self, tmp_path):
        rows = _high_ndvi_rows("parcel_01")
        _write_quality_csv(tmp_path, "parcel_01", rows)
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert result["verdict_code"] == VERDICT_CODES[result["verdict"]]


# ============================================================
# Commitment-window enforcement
# ============================================================

class TestCommitmentWindowEnforcement:
    def test_out_of_window_observations_excluded(self, tmp_path):
        rows = [
            ("parcel_01", "2024-02-01T00:00:00Z", "", 0.1, 1.0),  # before window
            ("parcel_01", "2024-04-01T00:00:00Z", "", 0.6, 1.0),
            ("parcel_01", "2024-04-05T00:00:00Z", "", 0.7, 1.0),
            ("parcel_01", "2024-04-10T00:00:00Z", "", 0.65, 1.0),
            ("parcel_01", "2024-04-15T00:00:00Z", "", 0.55, 1.0),
            ("parcel_01", "2024-12-01T00:00:00Z", "", 0.1, 1.0),  # after window
        ]
        _write_quality_csv(tmp_path, "parcel_01", rows)
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        # 4 in-window observations, but temporal coverage is low
        # (only 1-2 intervals of 25) => inconclusive
        assert result["verdict"] == "inconclusive"
        assert result["quality"]["valid_count"] == 4
        assert len(result["observations"]) == 4

    def test_invalid_window_returns_inconclusive(self, tmp_path):
        rows = _high_ndvi_rows("parcel_01")
        _write_quality_csv(tmp_path, "parcel_01", rows)
        bad_policy = dict(POLICY, window_start="not-a-date")
        result = verify_parcel("parcel_01", bad_policy, str(tmp_path))
        assert result["verdict"] == "inconclusive"
        assert result["reason_code"] == "INVALID_INPUT"


# ============================================================
# Evidence warnings preservation
# ============================================================

class TestEvidenceWarnings:
    def test_quality_metadata_available(self, tmp_path):
        rows = _high_ndvi_rows("parcel_01")
        _write_quality_csv(tmp_path, "parcel_01", rows)
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert result["quality"]["quality_metadata_available"] is True
        assert result["quality"]["evidence_quality"] == "assessed"

    def test_missing_quality_metadata_flagged(self, tmp_path):
        """CSV without valid_pixel_fraction is flagged as unknown quality."""
        path = tmp_path / "parcel_01_2024.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write("date,ndvi_mean\n")
            for d in SEASON_DATES:
                f.write(f"{d}T00:00:00Z,0.6\n")
        result = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert result["quality"]["quality_metadata_available"] is False
        assert result["quality"]["evidence_quality"] == "unknown"
        assert any(
            "valid_pixel_fraction" in w for w in result["quality"]["warnings"]
        )


# ============================================================
# Deterministic verification
# ============================================================

class TestDeterministicVerification:
    def test_same_data_same_result(self, tmp_path):
        rows = _high_ndvi_rows("parcel_01")
        _write_quality_csv(tmp_path, "parcel_01", rows)
        r1 = verify_parcel("parcel_01", POLICY, str(tmp_path))
        r2 = verify_parcel("parcel_01", POLICY, str(tmp_path))
        assert r1["verdict"] == r2["verdict"]
        assert r1["observations"] == r2["observations"]
        assert r1["quality"] == r2["quality"]

    @pytest.mark.parametrize("parcel_id", ALL_PARCELS)
    def test_all_parcels_deterministic(self, parcel_id, tmp_path):
        rows = _high_ndvi_rows(parcel_id)
        _write_quality_csv(tmp_path, parcel_id, rows)
        r1 = verify_parcel(parcel_id, POLICY, str(tmp_path))
        r2 = verify_parcel(parcel_id, POLICY, str(tmp_path))
        assert r1["verdict"] == r2["verdict"]
        assert r1["observations"] == r2["observations"]
