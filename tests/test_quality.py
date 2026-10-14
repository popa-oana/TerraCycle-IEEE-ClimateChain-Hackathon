"""
tests/test_quality.py — Day 4 tests for data quality, coverage and rules

Covers:
- NDVI formula and SCL masking policy primitives
- valid_pixel_fraction assessment (Rule C)
- temporal coverage calculation (Rule B)
- observation quality filtering
- integration of quality rules into verify_parcel()

All tests use synthetic fixtures only and never require a live Copernicus session.
No synthetic fixture is written into the real-data directories.
"""

import csv
import os
import sys
import tempfile
from datetime import datetime

from pathlib import Path

# Anchor imports to the repository root so the tests work regardless
# of the directory they are run from.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import pytest

from backend.ml.quality import (
    ACCEPTED_SCL_CLASSES,
    compute_ndvi,
    compute_temporal_coverage,
    evaluate_observation_quality,
    filter_observations_by_quality,
    is_scl_class_usable,
    merge_ndvi_and_coverage,
)
from backend.ml.rules import verify_parcel


# ============================================================
# Helpers
# ============================================================

def _write_csv(directory, filename, rows, columns):
    filepath = os.path.join(directory, filename)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
    return filepath


# ============================================================
# SECTION A: NDVI formula
# ============================================================

class TestNDVIFormula:
    def test_ndvi_basic(self):
        # red=0.1, nir=0.3 -> (0.3-0.1)/(0.3+0.1) = 0.5
        assert compute_ndvi(0.1, 0.3) == pytest.approx(0.5)

    def test_ndvi_negative(self):
        # red=0.3, nir=0.1 -> -0.5
        assert compute_ndvi(0.3, 0.1) == pytest.approx(-0.5)

    def test_ndvi_zero_denominator_returns_none(self):
        assert compute_ndvi(0.0, 0.0) is None
        assert compute_ndvi(-0.5, 0.5) is None

    def test_ndvi_missing_inputs(self):
        assert compute_ndvi(None, 0.3) is None
        assert compute_ndvi(0.1, None) is None

    def test_ndvi_equal_bands_is_zero(self):
        assert compute_ndvi(0.2, 0.2) == 0.0


# ============================================================
# SECTION B: SCL masking policy
# ============================================================

class TestSCLPolicy:
    def test_accepted_classes_are_4_and_5(self):
        assert ACCEPTED_SCL_CLASSES == (4, 5)

    def test_vegetation_and_bare_soil_usable(self):
        assert is_scl_class_usable(4) is True
        assert is_scl_class_usable(5) is True

    def test_clouds_and_others_not_usable(self):
        for scl in (0, 1, 2, 3, 6, 7, 8, 9, 10, 11):
            assert is_scl_class_usable(scl) is False, f"SCL {scl} must be excluded"


# ============================================================
# SECTION C: observation quality (Rule C)
# ============================================================

class TestObservationQuality:
    def test_full_coverage_passes(self):
        ok, reason = evaluate_observation_quality(1.0)
        assert ok is True

    def test_exactly_50_percent_passes(self):
        ok, _ = evaluate_observation_quality(0.50)
        assert ok is True

    def test_below_50_percent_fails(self):
        ok, reason = evaluate_observation_quality(0.49)
        assert ok is False
        assert "valid_pixel_fraction" in reason

    def test_zero_coverage_fails(self):
        ok, _ = evaluate_observation_quality(0.0)
        assert ok is False

    def test_missing_fraction_fails(self):
        ok, reason = evaluate_observation_quality(None)
        assert ok is False
        assert "Missing" in reason

    def test_nan_fraction_fails(self):
        ok, _ = evaluate_observation_quality(float("nan"))
        assert ok is False

    def test_out_of_range_fraction_fails(self):
        ok, _ = evaluate_observation_quality(1.5)
        assert ok is False
        ok2, _ = evaluate_observation_quality(-0.1)
        assert ok2 is False

    def test_custom_threshold(self):
        ok, _ = evaluate_observation_quality(0.30, min_valid_pixel_fraction=0.25)
        assert ok is True


# ============================================================
# SECTION D: temporal coverage (Rule B)
# ============================================================

class TestTemporalCoverage:
    def test_complete_coverage(self):
        # Window 2024-03-01 .. 2024-03-11 = 1 interval (10 days)
        dates = [datetime(2024, 3, 5)]
        result = compute_temporal_coverage(
            dates, datetime(2024, 3, 1), datetime(2024, 3, 11), interval_days=10
        )
        assert result["total_intervals"] == 1
        assert result["covered_intervals"] == 1
        assert result["temporal_coverage"] == 1.0

    def test_exactly_50_percent(self):
        # 20-day window => 2 intervals; one observation in the first => 0.5
        dates = [datetime(2024, 3, 5)]
        result = compute_temporal_coverage(
            dates, datetime(2024, 3, 1), datetime(2024, 3, 21), interval_days=10
        )
        assert result["total_intervals"] == 2
        assert result["covered_intervals"] == 1
        assert result["temporal_coverage"] == 0.5

    def test_less_than_50_percent(self):
        # 30-day window => 3 intervals; one covered => 0.333
        dates = [datetime(2024, 3, 5)]
        result = compute_temporal_coverage(
            dates, datetime(2024, 3, 1), datetime(2024, 3, 31), interval_days=10
        )
        assert result["total_intervals"] == 3
        assert result["temporal_coverage"] < 0.5

    def test_multiple_observations_same_interval_count_once(self):
        dates = [datetime(2024, 3, 2), datetime(2024, 3, 5), datetime(2024, 3, 9)]
        result = compute_temporal_coverage(
            dates, datetime(2024, 3, 1), datetime(2024, 3, 21), interval_days=10
        )
        assert result["covered_intervals"] == 1
        assert result["temporal_coverage"] == 0.5

    def test_missing_intervals(self):
        # Observations in interval 0 and 2 only, out of 3
        dates = [datetime(2024, 3, 2), datetime(2024, 3, 25)]
        result = compute_temporal_coverage(
            dates, datetime(2024, 3, 1), datetime(2024, 3, 31), interval_days=10
        )
        assert result["covered_intervals"] == 2
        assert result["temporal_coverage"] == round(2 / 3, 4)

    def test_empty_observations(self):
        result = compute_temporal_coverage(
            [], datetime(2024, 3, 1), datetime(2024, 3, 31), interval_days=10
        )
        assert result["covered_intervals"] == 0
        assert result["temporal_coverage"] == 0.0

    def test_boundary_start_inclusive_end_exclusive(self):
        # Observation exactly at window_start counts; at window_end does not.
        result_start = compute_temporal_coverage(
            [datetime(2024, 3, 1)], datetime(2024, 3, 1), datetime(2024, 3, 11)
        )
        assert result_start["covered_intervals"] == 1
        result_end = compute_temporal_coverage(
            [datetime(2024, 3, 11)], datetime(2024, 3, 1), datetime(2024, 3, 11)
        )
        assert result_end["covered_intervals"] == 0

    def test_invalid_window_returns_zero(self):
        result = compute_temporal_coverage(
            [datetime(2024, 3, 5)], datetime(2024, 3, 11), datetime(2024, 3, 1)
        )
        assert result["temporal_coverage"] == 0.0
        assert result["total_intervals"] == 0

    def test_result_within_zero_one(self):
        dates = [datetime(2024, 4, d) for d in (1, 11, 21, 25)]
        result = compute_temporal_coverage(
            dates, datetime(2024, 3, 1), datetime(2024, 6, 1), interval_days=10
        )
        assert 0.0 <= result["temporal_coverage"] <= 1.0


# ============================================================
# SECTION E: filtering observations by quality
# ============================================================

class TestFilterObservations:
    def test_marks_and_preserves_rows(self):
        df = pd.DataFrame(
            {
                "date": ["2024-04-01", "2024-04-05", "2024-04-10"],
                "ndvi_mean": [0.6, 0.5, 0.7],
                "valid_pixel_fraction": [0.9, 0.2, None],
            }
        )
        result = filter_observations_by_quality(df)
        assert len(result["df_valid"]) == 1
        assert len(result["df_invalid"]) == 2
        # Raw row count preserved across valid + invalid
        assert result["valid_count"] + result["invalid_count"] == len(df)
        # Marks present
        assert "is_valid_observation" in result["df_valid"].columns
        assert "quality_reason" in result["df_invalid"].columns

    def test_reasons_for_exclusion(self):
        df = pd.DataFrame(
            {
                "date": ["2024-04-01"],
                "ndvi_mean": [0.5],
                "valid_pixel_fraction": [None],
            }
        )
        result = filter_observations_by_quality(df)
        assert result["invalid_count"] == 1
        assert len(result["excluded_reasons"]) == 1


# ============================================================
# SECTION F: quality rules integrated into verify_parcel()
# ============================================================

_QUALITY_COLUMNS = ["date", "feature_index", "band_unnamed", "valid_pixel_fraction"]


class TestVerifyParcelQuality:

    def test_low_quality_observations_excluded(self):
        """Rule C: observations < 50% valid pixels are not valid evidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6, 0.9),
                ("2024-04-05T00:00:00.000Z", 0, 0.7, 0.2),   # rejected
                ("2024-04-10T00:00:00.000Z", 0, 0.65, 0.1),  # rejected
                ("2024-04-15T00:00:00.000Z", 0, 0.55, 0.3),  # rejected
                ("2024-04-20T00:00:00.000Z", 0, 0.8, 0.95),
            ]
            _write_csv(tmpdir, "parcel_01_2024.csv", rows, _QUALITY_COLUMNS)
            result = verify_parcel("parcel_01", {}, tmpdir)
            # Only 2 valid observations remain -> inconclusive
            assert result["verdict"] == "inconclusive"
            assert result["reason_code"] == "INSUFFICIENT_OBSERVATIONS"
            assert result["quality"]["quality_excluded_count"] == 3
            assert result["quality"]["valid_count"] == 2
            assert result["quality"]["evidence_quality"] == "assessed"

    def test_all_high_quality_can_be_conform(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6, 0.9),
                ("2024-04-05T00:00:00.000Z", 0, 0.7, 0.92),
                ("2024-04-10T00:00:00.000Z", 0, 0.65, 0.88),
                ("2024-04-15T00:00:00.000Z", 0, 0.55, 0.95),
                ("2024-04-20T00:00:00.000Z", 0, 0.8, 0.91),
            ]
            _write_csv(tmpdir, "parcel_01_2024.csv", rows, _QUALITY_COLUMNS)
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict"] == "conform"
            assert result["quality"]["quality_excluded_count"] == 0

    def test_missing_quality_metadata_is_flagged(self):
        """Old CSVs without valid_pixel_fraction are not treated as fully validated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6),
                ("2024-04-05T00:00:00.000Z", 0, 0.7),
                ("2024-04-10T00:00:00.000Z", 0, 0.65),
                ("2024-04-15T00:00:00.000Z", 0, 0.55),
                ("2024-04-20T00:00:00.000Z", 0, 0.8),
            ]
            _write_csv(
                tmpdir, "parcel_01_2024.csv", rows,
                ["date", "feature_index", "band_unnamed"],
            )
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["quality"]["evidence_quality"] == "unknown"
            assert result["quality"]["quality_metadata_available"] is False
            assert any("valid_pixel_fraction" in w for w in result["quality"]["warnings"])

    def test_temporal_coverage_insufficient(self):
        """Rule B: < 50% temporal coverage => inconclusive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 92-day window => 10 intervals. All obs in first interval => 0.1.
            rows = [
                ("2024-03-02T00:00:00.000Z", 0, 0.6, 0.9),
                ("2024-03-03T00:00:00.000Z", 0, 0.7, 0.9),
                ("2024-03-04T00:00:00.000Z", 0, 0.65, 0.9),
                ("2024-03-05T00:00:00.000Z", 0, 0.55, 0.9),
                ("2024-03-06T00:00:00.000Z", 0, 0.8, 0.9),
            ]
            _write_csv(tmpdir, "parcel_01_2024.csv", rows, _QUALITY_COLUMNS)
            policy = {"window_start": "2024-03-01", "window_end": "2024-06-01"}
            result = verify_parcel("parcel_01", policy, tmpdir)
            assert result["verdict"] == "inconclusive"
            assert result["reason_code"] == "INSUFFICIENT_TEMPORAL_COVERAGE"
            assert result["quality"]["temporal_coverage"] < 0.5

    def test_temporal_coverage_sufficient(self):
        """Rule B: >= 50% temporal coverage allows a normal verdict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 10 intervals; cover 5 distinct intervals => 0.5
            rows = [
                ("2024-03-02T00:00:00.000Z", 0, 0.6, 0.9),
                ("2024-03-12T00:00:00.000Z", 0, 0.7, 0.9),
                ("2024-03-22T00:00:00.000Z", 0, 0.65, 0.9),
                ("2024-04-02T00:00:00.000Z", 0, 0.55, 0.9),
                ("2024-04-12T00:00:00.000Z", 0, 0.8, 0.9),
            ]
            _write_csv(tmpdir, "parcel_01_2024.csv", rows, _QUALITY_COLUMNS)
            policy = {"window_start": "2024-03-01", "window_end": "2024-06-01"}
            result = verify_parcel("parcel_01", policy, tmpdir)
            assert result["quality"]["temporal_coverage"] >= 0.5
            assert result["verdict"] == "conform"

    def test_quality_column_all_missing_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [
                ("2024-04-01T00:00:00.000Z", 0, 0.6, ""),
                ("2024-04-05T00:00:00.000Z", 0, 0.7, ""),
                ("2024-04-10T00:00:00.000Z", 0, 0.65, ""),
                ("2024-04-15T00:00:00.000Z", 0, 0.55, ""),
                ("2024-04-20T00:00:00.000Z", 0, 0.8, ""),
            ]
            _write_csv(tmpdir, "parcel_01_2024.csv", rows, _QUALITY_COLUMNS)
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict"] == "inconclusive"
            assert result["quality"]["valid_count"] == 0

    def test_observations_include_quality_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [("2024-04-01T00:00:00.000Z", 0, 0.6, 0.9)]
            _write_csv(tmpdir, "parcel_01_2024.csv", rows, _QUALITY_COLUMNS)
            result = verify_parcel("parcel_01", {}, tmpdir)
            obs = result["observations"][0]
            assert obs["is_valid_observation"] is True
            assert obs["valid_pixel_fraction"] == 0.9

    def test_verdict_codes_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [("2024-04-01T00:00:00.000Z", 0, 0.6, 0.9)]
            _write_csv(tmpdir, "parcel_01_2024.csv", rows, _QUALITY_COLUMNS)
            result = verify_parcel("parcel_01", {}, tmpdir)
            assert result["verdict_code"] in (0, 1, 2)


# ============================================================
# SECTION G: export merge (mocked openEO aggregate_spatial outputs)
# ============================================================

class TestMergeExports:
    def _ndvi_export(self):
        # Mimics openEO aggregate_spatial CSV: date, feature_index, band_unnamed
        return pd.DataFrame(
            {
                "date": [
                    "2024-04-10T00:00:00.000Z",
                    "2024-04-01T00:00:00.000Z",
                    "2024-04-05T00:00:00.000Z",
                ],
                "feature_index": [0, 0, 0],
                "band_unnamed": [0.54, 0.60, 0.50],
            }
        )

    def _coverage_export(self):
        return pd.DataFrame(
            {
                "date": [
                    "2024-04-01T00:00:00.000Z",
                    "2024-04-05T00:00:00.000Z",
                    "2024-04-10T00:00:00.000Z",
                ],
                "feature_index": [0, 0, 0],
                "band_unnamed": [0.93, 0.41, 0.88],
            }
        )

    def test_schema_is_correct(self):
        merged = merge_ndvi_and_coverage(
            self._ndvi_export(), self._coverage_export(), "parcel_01"
        )
        assert list(merged.columns) == [
            "parcel_id",
            "acquired_at",
            "scene_id",
            "ndvi_mean",
            "valid_pixel_fraction",
        ]

    def test_rows_sorted_chronologically(self):
        merged = merge_ndvi_and_coverage(
            self._ndvi_export(), self._coverage_export(), "parcel_01"
        )
        dates = list(merged["acquired_at"])
        assert dates == sorted(dates)

    def test_values_matched_by_date(self):
        merged = merge_ndvi_and_coverage(
            self._ndvi_export(), self._coverage_export(), "parcel_01"
        )
        row = merged[merged["acquired_at"] == "2024-04-05T00:00:00Z"].iloc[0]
        assert row["ndvi_mean"] == pytest.approx(0.5)
        assert row["valid_pixel_fraction"] == pytest.approx(0.41)

    def test_scene_id_not_fabricated(self):
        merged = merge_ndvi_and_coverage(
            self._ndvi_export(), self._coverage_export(), "parcel_01"
        )
        assert merged["scene_id"].isna().all()

    def test_parcel_id_present(self):
        merged = merge_ndvi_and_coverage(
            self._ndvi_export(), self._coverage_export(), "parcel_01"
        )
        assert (merged["parcel_id"] == "parcel_01").all()

    def test_missing_columns_raise(self):
        with pytest.raises(ValueError):
            merge_ndvi_and_coverage(
                pd.DataFrame({"foo": [1]}),
                self._coverage_export(),
                "parcel_01",
            )

    def test_deterministic(self):
        a = merge_ndvi_and_coverage(
            self._ndvi_export(), self._coverage_export(), "parcel_01"
        )
        b = merge_ndvi_and_coverage(
            self._ndvi_export(), self._coverage_export(), "parcel_01"
        )
        pd.testing.assert_frame_equal(a, b)
