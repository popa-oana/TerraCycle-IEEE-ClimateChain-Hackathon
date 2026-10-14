"""
test_rules_pytest.py — Comprehensive pytest tests for the provisional verifier

Tests both verify_vegetation() and verify_parcel() from backend/ml/rules.py.
All tests use synthetic data and are deterministic, independent of live
Copernicus access, and reproducible.

Run with (from the repository root):
    .venv/Scripts/python.exe -m pytest tests/test_rules_pytest.py -v
"""

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

# Anchor imports to the repository root so the tests work regardless
# of the directory they are run from.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.rules import (
    VERDICT_CODES,
    VERDICTS,
    verify_parcel,
    verify_vegetation,
)


# ============================================================
# SECTION A: verify_vegetation() tests
# ============================================================

class TestVerifyVegetation:
    """Tests for the core verify_vegetation() function."""

    def test_clear_vegetation_returns_conform(self):
        """5 high-NDVI observations => conform."""
        result = verify_vegetation([0.5, 0.6, 0.7, 0.55, 0.65])
        assert result["verdict"] == "conform"
        assert result["valid_observations"] == 5
        assert result["vegetated_count"] == 5
        assert result["vegetated_fraction"] == 1.0

    def test_bare_soil_returns_nonconform(self):
        """5 low-NDVI observations => nonconform."""
        result = verify_vegetation([0.1, 0.2, 0.15, 0.18, 0.12])
        assert result["verdict"] == "nonconform"
        assert result["valid_observations"] == 5
        assert result["vegetated_count"] == 0

    def test_insufficient_observations_returns_inconclusive(self):
        """Fewer than 5 valid observations => inconclusive."""
        result = verify_vegetation([0.5, None, 0.6])
        assert result["verdict"] == "inconclusive"
        assert result["valid_observations"] == 2
        assert result["reason"] == "Insufficient valid NDVI observations"

    def test_mixed_observations_nonconform(self):
        """Mixed NDVI values below required_fraction => nonconform."""
        result = verify_vegetation([0.5, 0.1, 0.6, 0.1, 0.1])
        assert result["verdict"] == "nonconform"
        assert result["vegetated_count"] == 2
        assert result["vegetated_fraction"] == 0.4

    def test_boundary_values(self):
        """Values at the exact threshold (0.35)."""
        # 0.35 is NOT > 0.35, so 4 values at 0.35 and 1 at 0.36
        result = verify_vegetation([0.35, 0.35, 0.35, 0.35, 0.36])
        assert result["verdict"] == "nonconform"
        assert result["vegetated_count"] == 1  # only 0.36 is > 0.35

    def test_invalid_values_filtered(self):
        """None, out-of-range values are filtered out."""
        result = verify_vegetation([0.5, 0.6, None, 2.0, -1.5, 0.7, 0.8, 0.55])
        assert result["verdict"] == "conform"
        # Valid: 0.5, 0.6, 0.7, 0.8, 0.55 (5 values, all > 0.35)
        assert result["valid_observations"] == 5

    def test_empty_observations(self):
        """Empty list => inconclusive, no crash."""
        result = verify_vegetation([])
        assert result["verdict"] == "inconclusive"
        assert result["valid_observations"] == 0
        assert result["vegetated_count"] == 0
        assert result["vegetated_fraction"] == 0.0

    def test_all_none_observations(self):
        """All None values => inconclusive."""
        result = verify_vegetation([None, None, None])
        assert result["verdict"] == "inconclusive"
        assert result["valid_observations"] == 0

    def test_fewer_than_five_valid(self):
        """Exactly 4 valid observations => inconclusive (default min=5)."""
        result = verify_vegetation([0.5, 0.6, 0.7, 0.8])
        assert result["verdict"] == "inconclusive"
        assert result["valid_observations"] == 4

    def test_exactly_five_valid(self):
        """Exactly 5 valid observations with enough vegetation => conform."""
        result = verify_vegetation([0.5, 0.6, 0.7, 0.8, 0.9])
        assert result["verdict"] == "conform"
        assert result["valid_observations"] == 5

    def test_many_low_observations(self):
        """Many low-NDVI observations => nonconform."""
        result = verify_vegetation([0.1] * 20)
        assert result["verdict"] == "nonconform"
        assert result["valid_observations"] == 20
        assert result["vegetated_count"] == 0

    def test_many_high_observations(self):
        """Many high-NDVI observations => conform."""
        result = verify_vegetation([0.7] * 20)
        assert result["verdict"] == "conform"
        assert result["valid_observations"] == 20
        assert result["vegetated_count"] == 20

    def test_exactly_at_required_fraction(self):
        """Exactly 80% vegetated => conform."""
        # 4 out of 5 = 0.80 = required_fraction
        result = verify_vegetation([0.5, 0.5, 0.5, 0.5, 0.1])
        assert result["verdict"] == "conform"
        assert result["vegetated_fraction"] == 0.8

    def test_just_below_required_fraction(self):
        """Just below 80% vegetated => nonconform."""
        # 3 out of 5 = 0.60 < 0.80
        result = verify_vegetation([0.5, 0.5, 0.5, 0.1, 0.1])
        assert result["verdict"] == "nonconform"
        assert result["vegetated_fraction"] == 0.6

    def test_custom_thresholds(self):
        """Custom thresholds work correctly."""
        result = verify_vegetation(
            [0.3, 0.3, 0.3, 0.3, 0.3],
            ndvi_threshold=0.2,
            required_fraction=0.5,
        )
        assert result["verdict"] == "conform"
        assert result["thresholds"]["ndvi_threshold"] == 0.2
        assert result["thresholds"]["required_fraction"] == 0.5

    def test_custom_min_observations(self):
        """Custom min_observations threshold."""
        result = verify_vegetation(
            [0.5, 0.6, 0.7],
            min_observations=3,
        )
        assert result["verdict"] == "conform"

    def test_thresholds_in_output(self):
        """Thresholds are included in the output for reproducibility."""
        result = verify_vegetation([0.5, 0.6, 0.7, 0.8, 0.9])
        assert "thresholds" in result
        assert result["thresholds"]["ndvi_threshold"] == 0.35
        assert result["thresholds"]["required_fraction"] == 0.80
        assert result["thresholds"]["min_observations"] == 5

    def test_edge_ndvi_minus_one(self):
        """NDVI = -1.0 (exact boundary) is valid."""
        result = verify_vegetation([-1.0, -1.0, -1.0, -1.0, -1.0])
        assert result["verdict"] == "nonconform"
        assert result["valid_observations"] == 5

    def test_edge_ndvi_plus_one(self):
        """NDVI = 1.0 (exact boundary) is valid and vegetated."""
        result = verify_vegetation([1.0, 1.0, 1.0, 1.0, 1.0])
        assert result["verdict"] == "conform"
        assert result["valid_observations"] == 5


# ============================================================
# SECTION B: Verdict mapping tests
# ============================================================

class TestVerdictMapping:
    """Tests for the verdict mapping constants."""

    def test_verdict_codes_conform(self):
        assert VERDICT_CODES["conform"] == 0

    def test_verdict_codes_nonconform(self):
        assert VERDICT_CODES["nonconform"] == 1

    def test_verdict_codes_inconclusive(self):
        assert VERDICT_CODES["inconclusive"] == 2

    def test_verdicts_values(self):
        assert VERDICTS["CONFORM"] == "conform"
        assert VERDICTS["NONCONFORM"] == "nonconform"
        assert VERDICTS["INCONCLUSIVE"] == "inconclusive"

    def test_all_verdicts_have_codes(self):
        """Every verdict string has a corresponding numeric code."""
        for key, verdict_str in VERDICTS.items():
            assert verdict_str in VERDICT_CODES, \
                f"Verdict '{verdict_str}' missing from VERDICT_CODES"


# ============================================================
# SECTION C: verify_parcel() tests (with temp CSV files)
# ============================================================

def _create_csv(directory, filename, rows, columns=None):
    """Helper to create a CSV file with given data."""
    if columns is None:
        columns = ["date", "feature_index", "band_unnamed"]
    filepath = os.path.join(directory, filename)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
    return filepath


class TestVerifyParcel:
    """Tests for the verify_parcel() integration function."""

    def test_missing_csv_returns_inconclusive(self):
        """No CSV file => inconclusive with MISSING_EVIDENCE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict"] == "inconclusive"
            assert result["verdict_code"] == 2
            assert result["reason_code"] == "MISSING_EVIDENCE"

    def test_valid_csv_conform(self):
        """CSV with enough high-NDVI observations => conform."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict"] == "conform"
            assert result["verdict_code"] == 0

    def test_valid_csv_nonconform(self):
        """CSV with low-NDVI observations => nonconform."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.1),
                ("2024-04-05T00:00:00.000Z", 0, 0.15),
                ("2024-04-10T00:00:00.000Z", 0, 0.12),
                ("2024-04-15T00:00:00.000Z", 0, 0.2),
                ("2024-04-20T00:00:00.000Z", 0, 0.18),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict"] == "nonconform"
            assert result["verdict_code"] == 1

    def test_insufficient_observations_inconclusive(self):
        """Fewer than 5 valid observations => inconclusive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict"] == "inconclusive"
            assert result["verdict_code"] == 2

    def test_missing_columns_returns_inconclusive(self):
        """CSV with wrong column names => inconclusive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "parcel_01_2024.csv")
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["wrong_col1", "wrong_col2"])
                writer.writerow(["val1", "val2"])
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict"] == "inconclusive"
            assert result["reason_code"] == "INVALID_CSV_STRUCTURE"

    def test_empty_csv_returns_inconclusive(self):
        """CSV with headers but no data rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_csv(tmpdir, "parcel_01_2024.csv", [])
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict"] == "inconclusive"

    def test_band_unnamed_renamed(self):
        """band_unnamed column is correctly renamed to ndvi_mean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)
            # Should process successfully despite 'band_unnamed' column name
            assert result["verdict"] == "conform"
            assert result["quality"]["valid_count"] == 5

    def test_observations_sorted_chronologically(self):
        """Observations in output are sorted by date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create CSV with unsorted dates
            rows = [
                ("2024-06-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-01T00:00:00.000Z", 0, 0.7),
                ("2024-05-01T00:00:00.000Z", 0, 0.65),
                ("2024-03-01T00:00:00.000Z", 0, 0.55),
                ("2024-07-01T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)

            dates = [obs["acquired_at"] for obs in result["observations"]]
            assert dates == sorted(dates), "Observations must be sorted chronologically"

    def test_duplicate_timestamps_handled(self):
        """Duplicate timestamps are deduplicated (keep first)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-01T00:00:00.000Z", 0, 0.7),  # duplicate
                ("2024-04-05T00:00:00.000Z", 0, 0.65),
                ("2024-04-10T00:00:00.000Z", 0, 0.55),
                ("2024-04-15T00:00:00.000Z", 0, 0.8),
                ("2024-04-20T00:00:00.000Z", 0, 0.75),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["quality"]["valid_count"] == 5  # 6 - 1 duplicate = 5

    def test_invalid_ndvi_values_filtered(self):
        """NDVI values outside [-1, 1] are filtered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 2.0),   # invalid
                ("2024-04-10T00:00:00.000Z", 0, -1.5),   # invalid
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)
            # Only 3 valid => inconclusive
            assert result["verdict"] == "inconclusive"
            assert result["quality"]["excluded_count"] == 2

    def test_missing_ndvi_values_handled(self):
        """Empty NDVI cells are handled safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, ""),     # missing
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
                ("2024-04-25T00:00:00.000Z", 0, 0.7),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["quality"]["valid_count"] == 5
            assert result["quality"]["excluded_count"] == 1

    def test_prefers_full_season_csv(self):
        """Full-season CSV is preferred over June-only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create both files with different data
            full_rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            june_rows = [
                ("2024-06-01T00:00:00.000Z", 0, 0.1),
                ("2024-06-05T00:00:00.000Z", 0, 0.15),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", full_rows)
            _create_csv(tmpdir, "parcel_01_june_2024.csv", june_rows)

            result = verify_parcel("parcel_01", {}, tmpdir)
            # Full season has 5 high-NDVI observations => conform
            assert result["verdict"] == "conform"
            assert "2024" in result["source"]["csv_file"]

    def test_policy_parameters_passed(self):
        """Custom policy parameters are used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.3),
                ("2024-04-05T00:00:00.000Z", 0, 0.3),
                ("2024-04-10T00:00:00.000Z", 0, 0.3),
                ("2024-04-15T00:00:00.000Z", 0, 0.3),
                ("2024-04-20T00:00:00.000Z", 0, 0.3),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)

            # With default threshold (0.35), all would be below => nonconform
            result_default = verify_parcel("parcel_01", {}, tmpdir)
            assert result_default["verdict"] == "nonconform"

            # With lower threshold (0.2), all above => conform
            policy = {"ndvi_threshold": 0.2, "required_fraction": 0.5}
            result_custom = verify_parcel("parcel_01", policy, tmpdir)
            assert result_custom["verdict"] == "conform"

    def test_output_has_required_fields(self):
        """verify_parcel output contains all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)

            assert "verdict" in result
            assert "verdict_code" in result
            assert "reason_code" in result
            assert "reason" in result
            assert "observations" in result
            assert "quality" in result
            assert "model" in result
            assert "source" in result

    def test_verdict_code_matches_verdict(self):
        """verdict_code matches the numeric code for the verdict string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test conform
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict_code"] == VERDICT_CODES[result["verdict"]]

    def test_ndvi_mean_column_directly(self):
        """CSV with ndvi_mean column (not band_unnamed) works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(
                tmpdir, "parcel_01_2024.csv", rows,
                columns=["date", "feature_index", "ndvi_mean"]
            )
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict"] == "conform"


# ============================================================
# SECTION D: JSON output validation tests
# ============================================================

class TestJSONOutput:
    """Tests for the JSON output format."""

    def test_json_serializable(self):
        """verify_parcel output is JSON-serializable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)

            # Must not raise
            json_str = json.dumps(result, ensure_ascii=False)
            assert len(json_str) > 0

            # Must round-trip
            parsed = json.loads(json_str)
            assert parsed["verdict"] == result["verdict"]

    def test_observations_have_acquired_at_and_ndvi(self):
        """Each observation has acquired_at and ndvi_mean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            result = verify_parcel("parcel_01", {}, tmpdir)

            for obs in result["observations"]:
                assert "acquired_at" in obs
                assert "ndvi_mean" in obs
                assert -1 <= obs["ndvi_mean"] <= 1


# ============================================================
# SECTION E: Reproducibility tests
# ============================================================

class TestReproducibility:
    """Same inputs produce same outputs (deterministic)."""

    def test_same_data_same_verdict(self):
        """Running verify_vegetation twice with same data gives same result."""
        data = [0.5, 0.6, 0.7, None, 0.55, 0.65]
        r1 = verify_vegetation(data)
        r2 = verify_vegetation(data)
        assert r1 == r2

    def test_same_csv_same_parcel_verdict(self):
        """Running verify_parcel twice with same CSV gives same result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _create_csv(tmpdir, "parcel_01_2024.csv", rows)
            r1 = verify_parcel("parcel_01", {}, tmpdir)
            r2 = verify_parcel("parcel_01", {}, tmpdir)
            assert r1["verdict"] == r2["verdict"]
            assert r1["observations"] == r2["observations"]
