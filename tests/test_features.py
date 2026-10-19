"""
tests/test_features.py — Day 5B parcel-level satellite feature tests

Covers:
- NDVI statistics (mean/min/max/std/range)
- linear trend on equally and irregularly spaced dates
- single-observation and duplicate-date behaviour
- empty input
- multiple parcels remaining independent
- commitment-window filtering (inclusive start / exclusive end, UTC)
- timestamp ordering irrelevance
- missing / invalid measurements and quality aggregation
- defensive Rule C application
- deterministic output and raw-input preservation
- build_features.py script output and report

All fixtures are synthetic and live in temporary directories or in-memory.
No real data file is modified by these tests.
"""

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.features import (  # noqa: E402
    FEATURE_NAMES,
    build_features,
)

SCRIPT_COLUMNS = [
    "parcel_id",
    "acquired_at",
    "scene_id",
    "ndvi_mean",
    "valid_pixel_fraction",
]


def _load_build_script():
    spec = importlib.util.spec_from_file_location(
        "build_features_script", REPO_ROOT / "scripts" / "build_features.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_script = _load_build_script()


def _frame(rows):
    """rows: list of (parcel_id, acquired_at, ndvi_mean, valid_pixel_fraction)."""
    return pd.DataFrame(
        [
            {
                "parcel_id": parcel_id,
                "acquired_at": acquired_at,
                "scene_id": "",
                "ndvi_mean": ndvi,
                "valid_pixel_fraction": fraction,
            }
            for parcel_id, acquired_at, ndvi, fraction in rows
        ],
        columns=SCRIPT_COLUMNS,
    )


def _row(features, parcel_id="parcel_01"):
    return features.loc[features["parcel_id"] == parcel_id].iloc[0]


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(SCRIPT_COLUMNS)
        writer.writerows(rows)
    return path


# ============================================================
# Statistics and trend
# ============================================================

class TestStatisticsAndTrend:
    def test_ndvi_statistics(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.4, 0.9),
                ("parcel_01", "2024-01-05T00:00:00Z", 0.6, 0.8),
                ("parcel_01", "2024-01-07T00:00:00Z", 0.8, 0.7),
            ]
        )
        result = build_features(df, min_observations=5)
        features = result["features"]

        assert list(features.columns) == ["parcel_id", *FEATURE_NAMES]
        row = _row(features)
        assert row["ndvi_mean"] == pytest.approx(0.5)
        assert row["ndvi_min"] == pytest.approx(0.2)
        assert row["ndvi_max"] == pytest.approx(0.8)
        assert row["ndvi_range"] == pytest.approx(0.6)
        # Population standard deviation (ddof=0): sqrt(0.05).
        assert row["ndvi_std"] == pytest.approx(0.223607, abs=1e-6)
        assert row["observation_count"] == 4
        assert row["observation_span_days"] == pytest.approx(6.0)
        assert row["mean_valid_pixel_fraction"] == pytest.approx(0.85)
        assert row["min_valid_pixel_fraction"] == pytest.approx(0.7)

        diagnostics = result["diagnostics"].iloc[0]
        assert bool(diagnostics["meets_min_observations"]) is False
        assert diagnostics["evidence_sufficiency"] == "insufficient"

    def test_trend_equally_spaced(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.1, 1.0),
                ("parcel_01", "2024-01-02T00:00:00Z", 0.3, 1.0),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.5, 1.0),
            ]
        )
        features = build_features(df)["features"]
        assert _row(features)["ndvi_trend"] == pytest.approx(0.2)

    def test_trend_irregularly_spaced_dates(self):
        # x = 0, 1, 3 days; y = 0.2, 0.4, 0.5 -> slope 0.092857...
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_01", "2024-01-02T00:00:00Z", 0.4, 1.0),
                ("parcel_01", "2024-01-04T00:00:00Z", 0.5, 1.0),
            ]
        )
        features = build_features(df)["features"]
        assert _row(features)["ndvi_trend"] == pytest.approx(0.092857, abs=1e-6)

    def test_decreasing_trend_is_negative(self):
        df = _frame(
            [
                ("parcel_01", "2024-06-01T00:00:00Z", 0.8, 1.0),
                ("parcel_01", "2024-06-11T00:00:00Z", 0.5, 1.0),
                ("parcel_01", "2024-06-21T00:00:00Z", 0.2, 1.0),
            ]
        )
        features = build_features(df)["features"]
        assert _row(features)["ndvi_trend"] == pytest.approx(-0.03)

    def test_single_observation(self):
        df = _frame([("parcel_01", "2024-01-01T00:00:00Z", 0.42, 0.95)])
        result = build_features(df)
        row = _row(result["features"])

        assert row["observation_count"] == 1
        assert row["ndvi_mean"] == pytest.approx(0.42)
        assert row["ndvi_std"] == pytest.approx(0.0)
        assert row["ndvi_range"] == pytest.approx(0.0)
        assert row["observation_span_days"] == pytest.approx(0.0)
        assert pd.isna(row["ndvi_trend"])
        assert result["diagnostics"].iloc[0]["trend_defined"] == False  # noqa: E712

    def test_duplicate_dates_do_not_fabricate_a_trend(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_01", "2024-01-01T00:00:00Z", 0.4, 1.0),
            ]
        )
        result = build_features(df)
        row = _row(result["features"])

        assert row["observation_count"] == 2
        assert result["diagnostics"].iloc[0]["distinct_observation_dates"] == 1
        assert pd.isna(row["ndvi_trend"])

    def test_timestamp_ordering_does_not_change_features(self):
        rows = [
            ("parcel_01", "2024-01-05T00:00:00Z", 0.6, 0.9),
            ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
            ("parcel_01", "2024-01-03T00:00:00Z", 0.4, 0.8),
        ]
        forward = build_features(_frame(rows))["features"]
        reversed_ = build_features(_frame(list(reversed(rows))))["features"]
        pd.testing.assert_frame_equal(forward, reversed_)


# ============================================================
# Empty input, schema and validation
# ============================================================

class TestInputHandling:
    def test_empty_dataframe_with_columns(self):
        empty = pd.DataFrame(columns=SCRIPT_COLUMNS)
        result = build_features(empty)

        assert list(result["features"].columns) == ["parcel_id", *FEATURE_NAMES]
        assert len(result["features"]) == 0
        assert len(result["diagnostics"]) == 0
        assert result["counts"]["used_observation_count"] == 0

    def test_none_input(self):
        result = build_features(None)
        assert len(result["features"]) == 0
        assert len(result["diagnostics"]) == 0

    def test_missing_required_columns_raise(self):
        df = pd.DataFrame({"parcel_id": ["p1"], "ndvi_mean": [0.5]})
        with pytest.raises(ValueError, match="required columns"):
            build_features(df)

    def test_invalid_thresholds_raise(self):
        df = _frame([("parcel_01", "2024-01-01T00:00:00Z", 0.5, 1.0)])
        with pytest.raises(ValueError, match="min_valid_pixel_fraction"):
            build_features(df, min_valid_pixel_fraction=1.5)
        with pytest.raises(ValueError, match="min_observations"):
            build_features(df, min_observations=0)

    def test_invalid_window_raises(self):
        df = _frame([("parcel_01", "2024-01-01T00:00:00Z", 0.5, 1.0)])
        with pytest.raises(ValueError, match="both window_start and window_end"):
            build_features(df, window_start="2024-01-01")
        with pytest.raises(ValueError, match="strictly after"):
            build_features(
                df, window_start="2024-02-01", window_end="2024-01-01"
            )

    def test_missing_required_columns_script_returns_error(self, tmp_path):
        path = _write_csv(
            tmp_path / "observations_clean.csv",
            [["2024-01-01T00:00:00Z", 0.5]],
        )
        # Rewrite with the wrong schema on purpose.
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["acquired_at", "ndvi_mean"])
            writer.writerow(["2024-01-01T00:00:00Z", "0.5"])

        exit_code = build_script.main(
            [
                "--input", str(path),
                "--output", str(tmp_path / "out.csv"),
                "--report", str(tmp_path / "report.json"),
                "--config", str(REPO_ROOT / "backend/ml/processing_config.json"),
            ]
        )
        assert exit_code == 1


# ============================================================
# Multiple parcels and cross-contamination
# ============================================================

class TestParcelIndependence:
    def test_multiple_parcels_stay_independent(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.4, 1.0),
                ("parcel_02", "2024-01-01T00:00:00Z", 0.8, 0.5),
                ("parcel_02", "2024-01-03T00:00:00Z", 0.9, 0.6),
            ]
        )
        result = build_features(df)
        features = result["features"]

        assert features["parcel_id"].tolist() == ["parcel_01", "parcel_02"]
        assert _row(features, "parcel_01")["ndvi_mean"] == pytest.approx(0.3)
        assert _row(features, "parcel_02")["ndvi_mean"] == pytest.approx(0.85)
        assert _row(features, "parcel_01")["observation_count"] == 2
        assert _row(features, "parcel_02")["observation_count"] == 2
        assert _row(features, "parcel_02")["min_valid_pixel_fraction"] == pytest.approx(0.5)

    def test_rows_without_parcel_id_are_excluded(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                (None, "2024-01-03T00:00:00Z", 0.4, 1.0),
            ]
        )
        result = build_features(df)

        assert len(result["features"]) == 1
        assert result["counts"]["missing_parcel_id_excluded"] == 1
        assert _row(result["features"])["observation_count"] == 1


# ============================================================
# Quality handling
# ============================================================

class TestQualityHandling:
    def test_quality_features_aggregate(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 0.6),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.3, 0.8),
                ("parcel_01", "2024-01-05T00:00:00Z", 0.4, 1.0),
            ]
        )
        row = _row(build_features(df)["features"])
        assert row["mean_valid_pixel_fraction"] == pytest.approx(0.8)
        assert row["min_valid_pixel_fraction"] == pytest.approx(0.6)

    def test_below_threshold_observations_are_excluded(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 0.4),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.4, 0.9),
            ]
        )
        result = build_features(df, min_valid_pixel_fraction=0.5)
        row = _row(result["features"])

        assert row["observation_count"] == 1
        assert result["counts"]["quality_excluded"] == 1
        assert result["diagnostics"].iloc[0]["quality_excluded_count"] == 1
        assert row["mean_valid_pixel_fraction"] == pytest.approx(0.9)

    def test_missing_quality_value_is_excluded(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, None),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.4, 0.9),
            ]
        )
        result = build_features(df)
        row = _row(result["features"])

        assert row["observation_count"] == 1
        assert result["counts"]["quality_excluded"] == 1

    def test_quality_column_absent_keeps_ndvi_and_nulls_quality(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, None),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.4, None),
            ]
        ).drop(columns=["valid_pixel_fraction"])
        result = build_features(df)
        row = _row(result["features"])

        assert row["observation_count"] == 2
        assert row["ndvi_mean"] == pytest.approx(0.3)
        assert pd.isna(row["mean_valid_pixel_fraction"])
        assert pd.isna(row["min_valid_pixel_fraction"])
        assert result["quality_metadata_available"] is False
        assert result["diagnostics"].iloc[0]["quality_metadata_available"] == False  # noqa: E712

    def test_all_missing_quality_excludes_everything(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, None),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.4, None),
            ]
        )
        result = build_features(df)
        assert len(result["features"]) == 0
        assert result["counts"]["quality_excluded"] == 2

    def test_invalid_ndvi_rows_are_excluded(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 1.5, 1.0),
                ("parcel_01", "2024-01-03T00:00:00Z", None, 1.0),
                ("parcel_01", "2024-01-05T00:00:00Z", 0.5, 1.0),
            ]
        )
        result = build_features(df)
        row = _row(result["features"])

        assert row["observation_count"] == 1
        assert result["counts"]["invalid_ndvi_excluded"] == 2

    def test_unparseable_timestamp_rows_are_excluded(self):
        df = _frame(
            [
                ("parcel_01", "not-a-date", 0.4, 1.0),
                ("parcel_01", "2024-01-05T00:00:00Z", 0.5, 1.0),
            ]
        )
        result = build_features(df)
        assert result["counts"]["invalid_timestamp_excluded"] == 1
        assert _row(result["features"])["observation_count"] == 1


# ============================================================
# Commitment window
# ============================================================

class TestCommitmentWindow:
    def test_window_is_inclusive_start_exclusive_end(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.1, 1.0),  # start included
                ("parcel_01", "2024-01-05T00:00:00Z", 0.3, 1.0),
                ("parcel_01", "2024-01-10T00:00:00Z", 0.9, 1.0),  # end excluded
            ]
        )
        result = build_features(
            df, window_start="2024-01-01", window_end="2024-01-10"
        )
        row = _row(result["features"])

        assert row["observation_count"] == 2
        assert row["ndvi_max"] == pytest.approx(0.3)
        assert result["counts"]["out_of_window_excluded"] == 1

    def test_out_of_window_parcel_produces_no_features(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.1, 1.0),
                ("parcel_02", "2024-08-01T00:00:00Z", 0.5, 1.0),
            ]
        )
        result = build_features(
            df, window_start="2024-01-01", window_end="2024-02-01"
        )
        assert result["features"]["parcel_id"].tolist() == ["parcel_01"]
        assert result["counts"]["out_of_window_excluded"] == 1

    def test_no_window_uses_all_observations(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.1, 1.0),
                ("parcel_01", "2025-01-01T00:00:00Z", 0.3, 1.0),
            ]
        )
        result = build_features(df)
        assert _row(result["features"])["observation_count"] == 2

    def test_invalid_window_raises_instead_of_silently_widening(self):
        df = _frame([("parcel_01", "2024-01-01T00:00:00Z", 0.1, 1.0)])
        with pytest.raises(ValueError, match="both window_start and window_end"):
            build_features(df, window_start="2024-01-01")
        with pytest.raises(ValueError, match="strictly after"):
            build_features(
                df, window_start="2024-06-01", window_end="2024-01-01"
            )


# ============================================================
# Determinism, raw-preservation and script output
# ============================================================

class TestDeterminismAndScript:
    def test_repeated_build_is_identical(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-05T00:00:00Z", 0.6, 0.9),
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_02", "2024-01-02T00:00:00Z", 0.4, 0.85),
            ]
        )
        first = build_features(df)["features"].to_csv(index=False)
        second = build_features(df)["features"].to_csv(index=False)
        assert first == second

    def test_raw_input_is_not_modified_by_build_features(self):
        df = _frame(
            [("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0)]
        )
        before = df.copy(deep=True)
        build_features(df)
        pd.testing.assert_frame_equal(df, before)

    def _run_script(self, tmp_path, window_start="2024-01-01", window_end="2024-03-01"):
        input_path = _write_csv(
            tmp_path / "observations_clean.csv",
            [
                ["parcel_01", "2024-01-01T00:00:00Z", "", "0.2", "1.0"],
                ["parcel_01", "2024-01-15T00:00:00Z", "", "0.5", "0.9"],
                ["parcel_01", "2024-02-15T00:00:00Z", "", "0.8", "0.8"],
                ["parcel_02", "2024-01-10T00:00:00Z", "", "0.7", "1.0"],
            ],
        )
        output_path = tmp_path / "parcel_features.csv"
        report_path = tmp_path / "parcel_features_report.json"
        exit_code = build_script.main(
            [
                "--input", str(input_path),
                "--output", str(output_path),
                "--report", str(report_path),
                "--config", str(REPO_ROOT / "backend/ml/processing_config.json"),
                "--window-start", window_start,
                "--window-end", window_end,
            ]
        )
        return exit_code, input_path, output_path, report_path

    def test_script_writes_features_and_report_without_touching_input(self, tmp_path):
        exit_code, input_path, output_path, report_path = self._run_script(tmp_path)
        input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()

        assert exit_code == 0
        assert output_path.exists()
        assert report_path.exists()

        features = pd.read_csv(output_path)
        assert list(features.columns) == ["parcel_id", *FEATURE_NAMES]
        assert features["parcel_id"].tolist() == ["parcel_01", "parcel_02"]

        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["schema_version"] == "parcel-features-v1"
        assert report["parcel_count"] == 2
        assert report["input_sha256"] == input_hash
        assert report["output_sha256"] == hashlib.sha256(
            output_path.read_bytes()
        ).hexdigest()
        assert report["commitment_window"] == {
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-03-01T00:00:00Z",
            "convention": "inclusive start, exclusive end, UTC",
            "source": "backend/ml/processing_config.json time_interval",
        }

    def test_script_output_is_deterministic(self, tmp_path):
        _, input_path, output_path, report_path = self._run_script(tmp_path)
        first_features = output_path.read_bytes()
        first_report = report_path.read_bytes()

        build_script.main(
            [
                "--input", str(input_path),
                "--output", str(output_path),
                "--report", str(report_path),
                "--config", str(REPO_ROOT / "backend/ml/processing_config.json"),
                "--window-start", "2024-01-01",
                "--window-end", "2024-03-01",
            ]
        )
        assert output_path.read_bytes() == first_features
        assert report_path.read_bytes() == first_report

    def test_script_missing_input_returns_error(self, tmp_path):
        exit_code = build_script.main(
            [
                "--input", str(tmp_path / "missing.csv"),
                "--output", str(tmp_path / "out.csv"),
                "--report", str(tmp_path / "report.json"),
            ]
        )
        assert exit_code == 1
