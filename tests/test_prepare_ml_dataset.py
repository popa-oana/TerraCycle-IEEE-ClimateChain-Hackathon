"""
tests/test_prepare_ml_dataset.py — Day 5A dataset preparation tests

Covers:
- output schema and logical types
- chronological sorting
- duplicate handling (per parcel + timestamp)
- missing timestamps
- invalid / missing NDVI
- exactly 50% and below 50% pixel coverage
- missing quality metadata (unknown quality is insufficient)
- invalid valid_pixel_fraction
- empty datasets and honest blocker reporting
- multiple parcel identifiers
- source preference (quality over NDVI-only, full season over June)
- raw file preservation and deterministic output

All fixtures are synthetic and written to pytest temporary directories.
No real-data file is modified or created by these tests.
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


DATASET_COLUMNS = [
    "parcel_id",
    "acquired_at",
    "scene_id",
    "ndvi_mean",
    "valid_pixel_fraction",
]


def _load_prepare_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_ml_dataset_script",
        REPO_ROOT / "scripts" / "prepare_ml_dataset.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare_module = _load_prepare_module()


# ============================================================
# Helpers
# ============================================================

def _write_csv(directory, filename, rows, columns=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    columns = columns or DATASET_COLUMNS
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
    return path


def _quality_rows(*triples):
    """Build full-schema rows from (date, ndvi, fraction) triples."""
    return [
        ["parcel_01", date, "", ndvi, fraction]
        for date, ndvi, fraction in triples
    ]


def _run(tmp_path, input_dir=None, threshold=None, config=None):
    input_dir = Path(input_dir) if input_dir is not None else tmp_path / "ndvi"
    output = tmp_path / "observations_clean.csv"
    report_path = tmp_path / "observations_quality_report.json"
    report = prepare_module.prepare_ml_dataset(
        input_dir=input_dir,
        output_csv=output,
        report_json=report_path,
        config_path=config,
        min_valid_pixel_fraction=threshold,
    )
    return report, output, report_path


# ============================================================
# Schema, sorting and types
# ============================================================

class TestSchemaAndSorting:
    def test_output_schema_and_types(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [
                ["parcel_01", "2024-06-01T00:00:00Z", "S2B_MSIL2A_123",
                 "0.608048", "1.0"],
                ["parcel_01", "2024-06-06T00:00:00Z", "", "0.373463", "1.0"],
            ],
        )
        report, output, _ = _run(tmp_path)

        assert list(pd.read_csv(output).columns) == DATASET_COLUMNS
        df = pd.read_csv(
            output, dtype={"parcel_id": str, "scene_id": str},
            keep_default_na=False,
        )

        assert df["parcel_id"].tolist() == ["parcel_01", "parcel_01"]
        assert df["acquired_at"].tolist() == [
            "2024-06-01T00:00:00Z",
            "2024-06-06T00:00:00Z",
        ]
        # A real scene identifier is preserved; a missing one stays empty.
        assert df.loc[0, "scene_id"] == "S2B_MSIL2A_123"
        assert df.loc[1, "scene_id"] == ""
        assert pd.api.types.is_float_dtype(df["ndvi_mean"])
        assert pd.api.types.is_float_dtype(df["valid_pixel_fraction"])
        assert float(df.loc[0, "ndvi_mean"]) == pytest.approx(0.608048)
        assert float(df.loc[0, "valid_pixel_fraction"]) == pytest.approx(1.0)
        assert report["accepted_observation_count"] == 2

    def test_chronological_sorting_across_parcels(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [
                ["parcel_01", "2024-06-06T00:00:00Z", "", "0.30", "1.0"],
                ["parcel_01", "2024-06-01T00:00:00Z", "", "0.40", "1.0"],
            ],
        )
        _write_csv(
            tmp_path / "ndvi",
            "parcel_02_2024_quality.csv",
            [
                ["parcel_02", "2024-06-01T00:00:00Z", "", "0.50", "1.0"],
                ["parcel_02", "2024-05-01T00:00:00Z", "", "0.60", "1.0"],
            ],
        )
        _, output, _ = _run(tmp_path)
        df = pd.read_csv(output)

        assert df["acquired_at"].tolist() == [
            "2024-05-01T00:00:00Z",
            "2024-06-01T00:00:00Z",
            "2024-06-01T00:00:00Z",
            "2024-06-06T00:00:00Z",
        ]
        # Ties on the same timestamp are broken deterministically by parcel_id.
        assert df.loc[1, "parcel_id"] == "parcel_01"
        assert df.loc[2, "parcel_id"] == "parcel_02"


# ============================================================
# Duplicates and structural invalid rows
# ============================================================

class TestDuplicatesAndStructuralValidation:
    def test_duplicate_parcel_timestamp_keeps_first(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(
                ("2024-06-01T00:00:00Z", "0.40", "1.0"),
                ("2024-06-01T00:00:00Z", "0.60", "1.0"),
            ),
        )
        report, output, _ = _run(tmp_path)
        df = pd.read_csv(output)

        assert len(df) == 1
        assert float(df.loc[0, "ndvi_mean"]) == pytest.approx(0.40)
        assert report["excluded_by_stage"]["duplicate_parcel_timestamp"] == 1
        assert report["excluded_observation_count"] == 1

    def test_same_timestamp_different_parcels_is_not_a_duplicate(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [["parcel_01", "2024-06-01T00:00:00Z", "", "0.40", "1.0"]],
        )
        _write_csv(
            tmp_path / "ndvi",
            "parcel_02_2024_quality.csv",
            [["parcel_02", "2024-06-01T00:00:00Z", "", "0.50", "1.0"]],
        )
        report, output, _ = _run(tmp_path)

        assert len(pd.read_csv(output)) == 2
        assert report["excluded_by_stage"]["duplicate_parcel_timestamp"] == 0
        assert report["unique_parcel_count"] == 2

    def test_missing_and_unparseable_timestamps_are_excluded(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [
                ["parcel_01", "", "", "0.40", "1.0"],
                ["parcel_01", "not-a-date", "", "0.45", "1.0"],
                ["parcel_01", "2024-06-01T00:00:00Z", "", "0.50", "1.0"],
            ],
        )
        report, output, _ = _run(tmp_path)

        assert len(pd.read_csv(output)) == 1
        assert report["excluded_by_stage"]["missing_or_unparseable_timestamp"] == 2

    def test_missing_and_out_of_range_ndvi_are_excluded(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [
                ["parcel_01", "2024-06-01T00:00:00Z", "", "", "1.0"],
                ["parcel_01", "2024-06-06T00:00:00Z", "", "nan", "1.0"],
                ["parcel_01", "2024-06-11T00:00:00Z", "", "1.5", "1.0"],
                ["parcel_01", "2024-06-16T00:00:00Z", "", "-2", "1.0"],
                ["parcel_01", "2024-06-21T00:00:00Z", "", "0.5", "1.0"],
            ],
        )
        report, output, _ = _run(tmp_path)

        assert len(pd.read_csv(output)) == 1
        assert report["excluded_by_stage"]["missing_or_out_of_range_ndvi"] == 4

    def test_missing_required_columns_raise(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [["2024-06-01T00:00:00Z", "0.5"]],
            columns=["date", "something_else"],
        )
        with pytest.raises(ValueError, match="ndvi_mean"):
            _run(tmp_path)

    def test_parcel_id_mismatch_raises(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [["parcel_99", "2024-06-01T00:00:00Z", "", "0.5", "1.0"]],
        )
        with pytest.raises(ValueError, match="parcel_id"):
            _run(tmp_path)


# ============================================================
# Pixel-quality filtering (Rule C reuse)
# ============================================================

class TestPixelQuality:
    def test_exactly_fifty_percent_is_accepted(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(("2024-06-01T00:00:00Z", "0.50", "0.5")),
        )
        report, output, _ = _run(tmp_path)

        assert len(pd.read_csv(output)) == 1
        assert report["accepted_observation_count"] == 1
        assert report["excluded_by_stage"]["pixel_quality"] == 0

    def test_below_fifty_percent_is_excluded(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(("2024-06-01T00:00:00Z", "0.50", "0.4999")),
        )
        report, output, _ = _run(tmp_path)

        assert len(pd.read_csv(output)) == 0
        assert report["accepted_observation_count"] == 0
        assert report["excluded_by_stage"]["pixel_quality"] == 1
        assert (
            report["quality_exclusion_categories"][
                "below_min_valid_pixel_fraction"
            ]
            == 1
        )
        assert any(
            "0.4999" in reason
            for reason in report["quality_exclusion_reasons"]
        )

    def test_missing_quality_column_is_insufficient(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [
                ["2024-06-01T00:00:00Z", "0.50"],
                ["2024-06-06T00:00:00Z", "0.60"],
            ],
            columns=["date", "ndvi_mean"],
        )
        report, output, _ = _run(tmp_path)

        assert len(pd.read_csv(output)) == 0
        assert report["missing_quality_information_count"] == 2
        assert report["excluded_by_stage"]["pixel_quality"] == 2
        assert (
            report["quality_exclusion_categories"]["missing_quality_metadata"]
            == 2
        )
        assert report["suitable_for_feature_engineering"] is False
        assert report["blocker"] is not None

    def test_empty_quality_values_are_insufficient(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(
                ("2024-06-01T00:00:00Z", "0.50", ""),
                ("2024-06-06T00:00:00Z", "0.60", ""),
            ),
        )
        report, output, _ = _run(tmp_path)

        assert len(pd.read_csv(output)) == 0
        assert report["missing_quality_information_count"] == 2
        assert (
            report["quality_exclusion_categories"]["missing_quality_metadata"]
            == 2
        )

    def test_invalid_fraction_values_are_excluded(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(
                ("2024-06-01T00:00:00Z", "0.50", "1.2"),
                ("2024-06-06T00:00:00Z", "0.50", "-0.1"),
            ),
        )
        report, output, _ = _run(tmp_path)

        assert len(pd.read_csv(output)) == 0
        assert (
            report["quality_exclusion_categories"][
                "invalid_valid_pixel_fraction"
            ]
            == 2
        )
        assert report["missing_quality_information_count"] == 0

    def test_config_threshold_is_used_and_can_be_overridden(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(("2024-06-01T00:00:00Z", "0.50", "0.65")),
        )
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"min_valid_pixel_fraction": 0.70}), encoding="utf-8"
        )

        strict_report, strict_output, _ = _run(
            tmp_path, config=config
        )
        assert len(pd.read_csv(strict_output)) == 0
        assert strict_report["min_valid_pixel_fraction"] == pytest.approx(0.70)

        relaxed_report, relaxed_output, _ = _run(
            tmp_path, config=config, threshold=0.50
        )
        assert len(pd.read_csv(relaxed_output)) == 1
        assert relaxed_report["min_valid_pixel_fraction"] == pytest.approx(0.50)

    def test_invalid_threshold_raises(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(("2024-06-01T00:00:00Z", "0.50", "1.0")),
        )
        with pytest.raises(ValueError, match="min_valid_pixel_fraction"):
            _run(tmp_path, threshold=1.5)


# ============================================================
# Empty inputs, multiple parcels, source selection
# ============================================================

class TestEmptyAndSourceSelection:
    def test_empty_input_directory_reports_blocker(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        report, output, report_path = _run(tmp_path, input_dir=empty)

        df = pd.read_csv(output)
        assert list(df.columns) == DATASET_COLUMNS
        assert len(df) == 0
        assert report["original_observation_count"] == 0
        assert report["accepted_observation_count"] == 0
        assert report["unique_parcel_count"] == 0
        assert report["suitable_for_feature_engineering"] is False
        assert report["blocker"] is not None
        assert report_path.exists()
        assert json.loads(report_path.read_text(encoding="utf-8")) == report

    def test_multiple_parcels_are_preserved(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [["parcel_01", "2024-06-01T00:00:00Z", "", "0.40", "1.0"]],
        )
        _write_csv(
            tmp_path / "ndvi",
            "parcel_02_2024_quality.csv",
            [["parcel_02", "2024-06-01T00:00:00Z", "", "0.50", "1.0"]],
        )
        report, _, _ = _run(tmp_path)

        assert report["unique_parcel_count"] == 2
        assert set(report["observations_per_parcel"]) == {
            "parcel_01",
            "parcel_02",
        }
        assert all(
            entry["accepted_observations"] == 1
            for entry in report["observations_per_parcel"].values()
        )

    def test_quality_source_is_preferred_and_alternates_are_not_merged(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024.csv",
            [
                ["parcel_01", "2024-03-01T00:00:00Z", "", "0.20", ""],
                ["parcel_01", "2024-03-06T00:00:00Z", "", "0.25", ""],
            ],
        )
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            [["parcel_01", "2024-03-01T00:00:00Z", "", "0.20", "0.9"]],
        )
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_june_2024_quality.csv",
            [["parcel_01", "2024-06-01T00:00:00Z", "", "0.60", "1.0"]],
        )
        report, output, _ = _run(tmp_path)

        assert len(pd.read_csv(output)) == 1
        assert report["accepted_observation_count"] == 1
        # Only the preferred file was read; the June subset is not merged in.
        assert report["original_observation_count"] == 1
        assert (
            Path(report["source_files_used"]["parcel_01"]).name
            == "parcel_01_2024_quality.csv"
        )
        skipped_names = {
            Path(item["file"]).name for item in report["source_files_skipped"]
        }
        assert skipped_names == {
            "parcel_01_2024.csv",
            "parcel_01_june_2024_quality.csv",
        }

    def test_june_ndvi_filename_is_parsed_as_the_same_parcel(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_june_2024.csv",
            [
                ["2024-06-01T00:00:00.000Z", "0", "0.60"],
                ["2024-06-06T00:00:00.000Z", "0", "0.55"],
            ],
            columns=["date", "feature_index", "band_unnamed"],
        )
        report, output, _ = _run(tmp_path)

        assert list(report["source_files_used"]) == ["parcel_01"]
        assert report["source_parcel_count"] == 1
        # NDVI-only export: quality is unknown, so nothing is assumed valid.
        assert len(pd.read_csv(output)) == 0
        assert report["missing_quality_information_count"] == 2

    def test_unknown_csv_files_are_reported_not_read(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "notes.csv",
            [["a", "b"]],
            columns=["x", "y"],
        )
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(("2024-06-01T00:00:00Z", "0.50", "1.0")),
        )
        report, _, _ = _run(tmp_path)

        assert report["accepted_observation_count"] == 1
        assert len(report["ignored_files"]) == 1
        assert report["ignored_files"][0]["file"].endswith("notes.csv")


# ============================================================
# Reproducibility and raw-file preservation
# ============================================================

class TestReproducibilityAndPreservation:
    def test_raw_files_are_not_modified(self, tmp_path):
        raw = _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(
                ("2024-06-01T00:00:00Z", "0.50", "1.0"),
                ("2024-06-06T00:00:00Z", "0.60", "0.2"),
            ),
        )
        before_bytes = raw.read_bytes()
        before_hash = hashlib.sha256(before_bytes).hexdigest()

        _run(tmp_path)

        assert raw.read_bytes() == before_bytes
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == before_hash

    def test_output_is_deterministic(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(
                ("2024-06-06T00:00:00Z", "0.60", "0.9"),
                ("2024-06-01T00:00:00Z", "0.50", "1.0"),
                ("2024-06-01T00:00:00Z", "0.55", "0.8"),
            ),
        )

        report_one, output_one, report_path_one = _run(tmp_path)
        first_csv = output_one.read_bytes()
        first_report = report_path_one.read_bytes()

        report_two, output_two, report_path_two = _run(tmp_path)

        assert output_two.read_bytes() == first_csv
        assert report_path_two.read_bytes() == first_report
        assert report_one == report_two
        assert report_one["dataset_sha256"] == hashlib.sha256(
            first_csv
        ).hexdigest()

    def test_counts_reconcile(self, tmp_path):
        _write_csv(
            tmp_path / "ndvi",
            "parcel_01_2024_quality.csv",
            _quality_rows(
                ("2024-06-01T00:00:00Z", "0.50", "1.0"),
                ("2024-06-06T00:00:00Z", "", "1.0"),
                ("2024-06-11T00:00:00Z", "0.55", "0.2"),
                ("2024-06-16T00:00:00Z", "0.60", ""),
            ),
        )
        report, _, _ = _run(tmp_path)

        assert report["original_observation_count"] == 4
        assert report["accepted_observation_count"] == 1
        assert report["excluded_observation_count"] == 3
        assert sum(report["excluded_by_stage"].values()) == 3
        assert report["accepted_date_range"] == {
            "start": "2024-06-01T00:00:00Z",
            "end": "2024-06-01T00:00:00Z",
        }
