"""
tests/test_multi_parcel.py — Day 5D multi-parcel combination tests

Covers:
- Four independent parcel inputs combined correctly
- Preservation of all four parcel IDs
- No cross-parcel contamination
- Duplicate handling within and across parcels
- Empty and missing input handling
- Commitment-window filtering across parcels
- Deterministic output
- Preservation of raw inputs

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

from backend.ml.features import FEATURE_NAMES, build_features  # noqa: E402
from backend.ml.quality import filter_observations_by_quality  # noqa: E402

SCRIPT_COLUMNS = [
    "parcel_id",
    "acquired_at",
    "scene_id",
    "ndvi_mean",
    "valid_pixel_fraction",
]


def _load_prepare_script():
    spec = importlib.util.spec_from_file_location(
        "prepare_ml_dataset_script", REPO_ROOT / "scripts" / "prepare_ml_dataset.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_build_script():
    spec = importlib.util.spec_from_file_location(
        "build_features_script", REPO_ROOT / "scripts" / "build_features.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare_script = _load_prepare_script()
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


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(SCRIPT_COLUMNS)
        writer.writerows(rows)
    return path


# ============================================================
# Multi-parcel combination
# ============================================================

class TestMultiParcelCombination:
    def test_four_parcels_preserved(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_02", "2024-01-01T00:00:00Z", 0.4, 1.0),
                ("parcel_03", "2024-01-01T00:00:00Z", 0.6, 1.0),
                ("parcel_04", "2024-01-01T00:00:00Z", 0.8, 1.0),
            ]
        )
        result = build_features(df)
        features = result["features"]
        assert features["parcel_id"].tolist() == [
            "parcel_01", "parcel_02", "parcel_03", "parcel_04"
        ]

    def test_no_cross_parcel_contamination(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.1, 1.0),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.3, 1.0),
                ("parcel_02", "2024-01-01T00:00:00Z", 0.7, 1.0),
                ("parcel_02", "2024-01-03T00:00:00Z", 0.9, 1.0),
            ]
        )
        result = build_features(df)
        features = result["features"]

        p1 = features[features["parcel_id"] == "parcel_01"].iloc[0]
        p2 = features[features["parcel_id"] == "parcel_02"].iloc[0]

        assert p1["ndvi_mean"] == pytest.approx(0.2)
        assert p2["ndvi_mean"] == pytest.approx(0.8)
        assert p1["observation_count"] == 2
        assert p2["observation_count"] == 2

    def test_same_date_different_parcels_not_deduplicated(self):
        """Two parcels with the same acquisition date must both be kept."""
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.3, 1.0),
                ("parcel_02", "2024-01-01T00:00:00Z", 0.7, 1.0),
            ]
        )
        result = build_features(df)
        features = result["features"]
        assert len(features) == 2
        assert features["observation_count"].tolist() == [1, 1]

    def test_duplicate_dates_within_parcel_deduplicated(self):
        """Duplicate dates within the same parcel are averaged for trend."""
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_01", "2024-01-01T00:00:00Z", 0.4, 1.0),
                ("parcel_01", "2024-01-03T00:00:00Z", 0.6, 1.0),
            ]
        )
        result = build_features(df)
        row = result["features"].iloc[0]
        # 3 rows but 2 distinct dates; observation_count = 3 (all rows kept)
        assert row["observation_count"] == 3
        assert result["diagnostics"].iloc[0]["distinct_observation_dates"] == 2


# ============================================================
# Empty and missing input
# ============================================================

class TestEmptyAndMissingInput:
    def test_empty_dataframe(self):
        empty = pd.DataFrame(columns=SCRIPT_COLUMNS)
        result = build_features(empty)
        assert len(result["features"]) == 0
        assert len(result["diagnostics"]) == 0

    def test_none_input(self):
        result = build_features(None)
        assert len(result["features"]) == 0

    def test_single_parcel_only(self):
        df = _frame([("parcel_01", "2024-01-01T00:00:00Z", 0.5, 1.0)])
        result = build_features(df)
        assert len(result["features"]) == 1
        assert result["features"].iloc[0]["parcel_id"] == "parcel_01"

    def test_missing_input_file_script(self, tmp_path):
        exit_code = build_script.main(
            [
                "--input", str(tmp_path / "missing.csv"),
                "--output", str(tmp_path / "out.csv"),
                "--report", str(tmp_path / "report.json"),
            ]
        )
        assert exit_code == 1


# ============================================================
# Commitment window
# ============================================================

class TestCommitmentWindow:
    def test_window_filters_all_parcels(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_01", "2024-01-05T00:00:00Z", 0.4, 1.0),
                ("parcel_02", "2024-01-01T00:00:00Z", 0.6, 1.0),
                ("parcel_02", "2024-01-05T00:00:00Z", 0.8, 1.0),
            ]
        )
        result = build_features(
            df, window_start="2024-01-01", window_end="2024-01-03"
        )
        features = result["features"]
        assert features["observation_count"].tolist() == [1, 1]

    def test_out_of_window_parcel_excluded(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_02", "2024-06-01T00:00:00Z", 0.6, 1.0),
            ]
        )
        result = build_features(
            df, window_start="2024-01-01", window_end="2024-02-01"
        )
        assert result["features"]["parcel_id"].tolist() == ["parcel_01"]
        assert result["counts"]["out_of_window_excluded"] == 1


# ============================================================
# Determinism and raw preservation
# ============================================================

class TestDeterminismAndRawPreservation:
    def test_repeated_build_is_identical(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_02", "2024-01-01T00:00:00Z", 0.4, 1.0),
                ("parcel_03", "2024-01-01T00:00:00Z", 0.6, 1.0),
                ("parcel_04", "2024-01-01T00:00:00Z", 0.8, 1.0),
            ]
        )
        first = build_features(df)["features"].to_csv(index=False)
        second = build_features(df)["features"].to_csv(index=False)
        assert first == second

    def test_raw_input_not_modified(self):
        df = _frame(
            [
                ("parcel_01", "2024-01-01T00:00:00Z", 0.2, 1.0),
                ("parcel_02", "2024-01-01T00:00:00Z", 0.4, 1.0),
            ]
        )
        before = df.copy(deep=True)
        build_features(df)
        pd.testing.assert_frame_equal(df, before)

    def test_prepare_script_preserves_raw_files(self, tmp_path):
        """Run prepare_ml_dataset.py and verify raw inputs are unchanged."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_csv(
            raw_dir / "parcel_01_2024_quality.csv",
            [
                ["parcel_01", "2024-01-01T00:00:00Z", "", "0.5", "1.0"],
                ["parcel_01", "2024-01-03T00:00:00Z", "", "0.6", "1.0"],
            ],
        )
        _write_csv(
            raw_dir / "parcel_02_2024_quality.csv",
            [
                ["parcel_02", "2024-01-01T00:00:00Z", "", "0.7", "1.0"],
                ["parcel_02", "2024-01-03T00:00:00Z", "", "0.8", "1.0"],
            ],
        )

        raw_before = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in raw_dir.glob("*.csv")
        }

        out_csv = tmp_path / "observations_clean.csv"
        out_report = tmp_path / "report.json"
        exit_code = prepare_script.main(
            [
                "--input-dir", str(raw_dir),
                "--output", str(out_csv),
                "--report", str(out_report),
                "--config", str(REPO_ROOT / "backend/ml/processing_config.json"),
            ]
        )
        assert exit_code == 0
        assert out_csv.exists()
        assert out_report.exists()

        raw_after = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in raw_dir.glob("*.csv")
        }
        assert raw_before == raw_after

        # Verify both parcels in output
        df = pd.read_csv(out_csv)
        assert df["parcel_id"].nunique() == 2
        assert set(df["parcel_id"].unique()) == {"parcel_01", "parcel_02"}
