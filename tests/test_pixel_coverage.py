"""
tests/test_pixel_coverage.py — Task 3A: real valid_pixel_fraction extraction

Covers, with synthetic fixtures only (never written into data/):
- Sentinel-2 SCL validity classification (classes 4/5 valid)
- SCL eligibility classification for the coverage denominator (1..11
  observed, 0/None/NaN excluded)
- Numerator/denominator fraction logic, including edge cases:
  completely valid parcel, partially cloudy parcel, completely unusable
  observation, missing SCL information, zero eligible pixels
- Timestamp alignment between the coverage series and the NDVI series
- Fraction values always within [0, 1]
- Offline construction of the openEO processing graphs (no authentication,
  no batch job): expected processes, SCL class constants, identical parcel
  geometry for numerator and denominator, explicit 10 m/20 m resampling of
  the SCL mask, and JSON serializability

Static graph construction does NOT prove that server-side execution will
succeed; that requires a live Copernicus job (out of scope here).
"""

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import pytest

from backend.ml.quality import (
    ACCEPTED_SCL_CLASSES,
    ELIGIBLE_SCL_CLASSES,
    compute_valid_pixel_fraction,
    coverage_means_to_fraction,
    is_scl_class_eligible,
    is_scl_class_usable,
    merge_ndvi_and_coverage,
)


# ============================================================
# Import the export script (scripts/ is not a package)
# ============================================================

def _load_export_module():
    spec = importlib.util.spec_from_file_location(
        "export_ndvi_script", REPO_ROOT / "scripts" / "export_ndvi.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export_mod = _load_export_module()


# ============================================================
# Helpers
# ============================================================

def _raw_export(dates, values) -> pd.DataFrame:
    """Mimic an openEO aggregate_spatial CSV: date, feature_index, band_unnamed."""
    return pd.DataFrame(
        {
            "date": dates,
            "feature_index": [0] * len(dates),
            "band_unnamed": values,
        }
    )


def _all_processes(graph: dict) -> set:
    """Recursively collect every process_id in a serialized process graph."""
    found = set()
    if isinstance(graph, dict):
        pid = graph.get("process_id")
        if isinstance(pid, str):
            found.add(pid)
        for value in graph.values():
            found |= _all_processes(value)
    elif isinstance(graph, list):
        for item in graph:
            found |= _all_processes(item)
    return found


def _find_nodes(graph: dict, process_id: str) -> list:
    """Recursively collect every node dict for a given process_id."""
    found = []
    if isinstance(graph, dict):
        if graph.get("process_id") == process_id:
            found.append(graph)
        for value in graph.values():
            found.extend(_find_nodes(value, process_id))
    elif isinstance(graph, list):
        for item in graph:
            found.extend(_find_nodes(item, process_id))
    return found


def _eq_constants(graph: dict) -> set:
    """Collect the constant compared in every `eq` node."""
    return {
        node["arguments"]["y"]
        for node in _find_nodes(graph, "eq")
        if isinstance(node["arguments"].get("y"), (int, float))
    }


# ============================================================
# SECTION A: SCL validity classification
# ============================================================

class TestSCLValidityClassification:
    def test_valid_classes_are_exactly_4_and_5(self):
        assert ACCEPTED_SCL_CLASSES == (4, 5)
        assert [c for c in range(-1, 13) if is_scl_class_usable(c)] == [4, 5]

    @pytest.mark.parametrize("scl_class", [0, 1, 2, 3, 6, 7, 8, 9, 10, 11])
    def test_non_vegetation_classes_not_valid(self, scl_class):
        assert is_scl_class_usable(scl_class) is False


# ============================================================
# SECTION B: SCL eligibility classification (denominator)
# ============================================================

class TestSCLEligibilityClassification:
    def test_eligible_classes_are_1_to_11(self):
        assert ELIGIBLE_SCL_CLASSES == tuple(range(1, 12))
        assert [c for c in range(0, 13) if is_scl_class_eligible(c)] == list(range(1, 12))

    def test_no_data_class_zero_not_eligible(self):
        assert is_scl_class_eligible(0) is False

    def test_missing_values_not_eligible(self):
        assert is_scl_class_eligible(float("nan")) is False
        assert is_scl_class_eligible(None) is False

    def test_every_valid_class_is_also_eligible(self):
        for scl_class in ACCEPTED_SCL_CLASSES:
            assert is_scl_class_usable(scl_class)
            assert is_scl_class_eligible(scl_class)

    def test_cloudy_but_observed_is_eligible_not_valid(self):
        for scl_class in (3, 8, 9, 10):
            assert is_scl_class_eligible(scl_class) is True
            assert is_scl_class_usable(scl_class) is False


# ============================================================
# SECTION C: numerator / denominator fraction logic
# ============================================================

class TestComputeValidPixelFraction:
    def test_completely_valid_parcel(self):
        # Every observed pixel is SCL 4/5: fraction must be exactly 1.0
        assert compute_valid_pixel_fraction(1.0, 1.0) == 1.0
        assert compute_valid_pixel_fraction(0.93, 0.93) == 1.0

    def test_partially_cloudy_parcel(self):
        # 60 of 100 observed pixels valid -> 0.6
        assert compute_valid_pixel_fraction(0.6, 1.0) == pytest.approx(0.6)
        # Ratio of means == ratio of counts on the same grid:
        # 30 valid out of 60 eligible -> means 0.3 and 0.6 -> 0.5
        assert compute_valid_pixel_fraction(0.3, 0.6) == pytest.approx(0.5)

    def test_completely_unusable_observation(self):
        # Observed but all cloudy/shadowed: eligible > 0, valid == 0 -> 0.0
        assert compute_valid_pixel_fraction(0.0, 1.0) == 0.0
        assert compute_valid_pixel_fraction(0.0, 0.42) == 0.0

    def test_missing_scl_information_returns_none(self):
        assert compute_valid_pixel_fraction(None, 1.0) is None
        assert compute_valid_pixel_fraction(0.5, None) is None
        assert compute_valid_pixel_fraction(float("nan"), 1.0) is None
        assert compute_valid_pixel_fraction(0.5, float("nan")) is None

    def test_zero_eligible_pixels_returns_none(self):
        assert compute_valid_pixel_fraction(0.0, 0.0) is None
        assert compute_valid_pixel_fraction(None, 0.0) is None
        assert compute_valid_pixel_fraction(0.0, -0.1) is None

    def test_non_numeric_inputs_return_none(self):
        assert compute_valid_pixel_fraction("x", 1.0) is None
        assert compute_valid_pixel_fraction(0.5, "y") is None

    def test_result_always_between_zero_and_one(self):
        cases = [
            (0.0, 1.0), (1.0, 1.0), (0.37, 1.0), (0.6, 0.9),
            (1.0, 0.5),   # server quirk: numerator > denominator -> clamp
            (1.2, 1.0),   # numerator > 1 -> clamp
            (-0.2, 1.0),  # negative numerator -> clamp
        ]
        for valid_mean, eligible_mean in cases:
            fraction = compute_valid_pixel_fraction(valid_mean, eligible_mean)
            assert fraction is not None, (valid_mean, eligible_mean)
            assert 0.0 <= fraction <= 1.0, (valid_mean, eligible_mean, fraction)

    def test_no_fraction_fabricated_on_missing_or_zero(self):
        for args in [(None, 1.0), (0.5, None), (float("nan"), 1.0),
                     (0.0, 0.0), (0.5, 0.0)]:
            assert compute_valid_pixel_fraction(*args) is None, args


# ============================================================
# SECTION D: coverage series from the two raw openEO exports
# ============================================================

class TestCoverageMeansToFraction:
    def test_fraction_per_date(self):
        valid = _raw_export(
            ["2024-06-01T00:00:00.000Z", "2024-06-11T00:00:00.000Z"],
            [1.0, 0.6],
        )
        eligible = _raw_export(
            ["2024-06-01T00:00:00.000Z", "2024-06-11T00:00:00.000Z"],
            [1.0, 1.0],
        )
        coverage = coverage_means_to_fraction(valid, eligible)
        assert list(coverage.columns) == ["date", "valid_pixel_fraction"]
        assert len(coverage) == 2
        values = dict(zip(coverage["date"].dt.strftime("%Y-%m-%d"),
                          coverage["valid_pixel_fraction"]))
        assert values["2024-06-01"] == pytest.approx(1.0)
        assert values["2024-06-11"] == pytest.approx(0.6)

    def test_zero_eligible_yields_nan_not_fabricated(self):
        valid = _raw_export(["2024-06-01T00:00:00.000Z"], [0.0])
        eligible = _raw_export(["2024-06-01T00:00:00.000Z"], [0.0])
        coverage = coverage_means_to_fraction(valid, eligible)
        assert len(coverage) == 1
        assert pd.isna(coverage["valid_pixel_fraction"].iloc[0])

    def test_missing_scl_value_yields_nan(self):
        # openEO writes an empty cell when the aggregate could not be computed.
        valid = _raw_export(["2024-06-01T00:00:00.000Z"], [None])
        eligible = _raw_export(["2024-06-01T00:00:00.000Z"], [None])
        coverage = coverage_means_to_fraction(valid, eligible)
        assert pd.isna(coverage["valid_pixel_fraction"].iloc[0])

    def test_dates_present_in_only_one_export_are_dropped(self):
        valid = _raw_export(
            ["2024-06-01T00:00:00.000Z", "2024-06-11T00:00:00.000Z"],
            [1.0, 1.0],
        )
        eligible = _raw_export(
            ["2024-06-01T00:00:00.000Z", "2024-06-21T00:00:00.000Z"],
            [1.0, 1.0],
        )
        coverage = coverage_means_to_fraction(valid, eligible)
        dates = coverage["date"].dt.strftime("%Y-%m-%d").tolist()
        assert dates == ["2024-06-01"]

    def test_output_sorted_and_within_zero_one(self):
        valid = _raw_export(
            ["2024-06-21T00:00:00.000Z", "2024-06-01T00:00:00.000Z",
             "2024-06-11T00:00:00.000Z"],
            [0.2, 1.0, 0.55],
        )
        eligible = _raw_export(
            ["2024-06-21T00:00:00.000Z", "2024-06-01T00:00:00.000Z",
             "2024-06-11T00:00:00.000Z"],
            [1.0, 1.0, 1.0],
        )
        coverage = coverage_means_to_fraction(valid, eligible)
        dates = coverage["date"].tolist()
        assert dates == sorted(dates)
        for value in coverage["valid_pixel_fraction"]:
            assert value is None or pd.isna(value) or 0.0 <= value <= 1.0

    def test_deterministic(self):
        valid = _raw_export(["2024-06-01T00:00:00.000Z"], [0.4])
        eligible = _raw_export(["2024-06-01T00:00:00.000Z"], [0.8])
        a = coverage_means_to_fraction(valid, eligible)
        b = coverage_means_to_fraction(valid, eligible)
        pd.testing.assert_frame_equal(a, b)

    def test_missing_columns_raise(self):
        with pytest.raises(ValueError):
            coverage_means_to_fraction(
                pd.DataFrame({"foo": [1]}),
                _raw_export(["2024-06-01T00:00:00.000Z"], [1.0]),
            )


# ============================================================
# SECTION E: timestamp alignment with the NDVI series
# ============================================================

class TestTimestampAlignment:
    def _ndvi_raw(self):
        # Deliberately unsorted, like a raw openEO export.
        return _raw_export(
            ["2024-06-11T00:00:00.000Z", "2024-06-01T00:00:00.000Z",
             "2024-06-21T00:00:00.000Z"],
            [0.4, 0.6, 0.3],
        )

    def _coverage(self):
        # Coverage covers a subset (06-01, 06-11) plus an extra date (06-16).
        valid = _raw_export(
            ["2024-06-11T00:00:00.000Z", "2024-06-01T00:00:00.000Z",
             "2024-06-16T00:00:00.000Z"],
            [0.5, 1.0, 0.7],
        )
        eligible = _raw_export(
            ["2024-06-11T00:00:00.000Z", "2024-06-01T00:00:00.000Z",
             "2024-06-16T00:00:00.000Z"],
            [1.0, 1.0, 1.0],
        )
        return coverage_means_to_fraction(valid, eligible)

    def test_merged_dates_are_sorted_intersection(self):
        merged = merge_ndvi_and_coverage(self._ndvi_raw(), self._coverage(),
                                          "parcel_01")
        assert list(merged.columns) == [
            "parcel_id", "acquired_at", "scene_id",
            "ndvi_mean", "valid_pixel_fraction",
        ]
        # Inner join on acquisition date: 06-16 has no NDVI row, 06-21 has
        # no coverage row -> only 06-01 and 06-11 survive, chronologically.
        assert merged["acquired_at"].tolist() == [
            "2024-06-01T00:00:00Z", "2024-06-11T00:00:00Z"
        ]

    def test_fraction_matches_its_own_date(self):
        merged = merge_ndvi_and_coverage(self._ndvi_raw(), self._coverage(),
                                          "parcel_01")
        row_01 = merged[merged["acquired_at"] == "2024-06-01T00:00:00Z"].iloc[0]
        row_11 = merged[merged["acquired_at"] == "2024-06-11T00:00:00Z"].iloc[0]
        assert row_01["ndvi_mean"] == pytest.approx(0.6)
        assert row_01["valid_pixel_fraction"] == pytest.approx(1.0)
        assert row_11["ndvi_mean"] == pytest.approx(0.4)
        assert row_11["valid_pixel_fraction"] == pytest.approx(0.5)

    def test_merged_fractions_within_zero_one(self):
        merged = merge_ndvi_and_coverage(self._ndvi_raw(), self._coverage(),
                                          "parcel_01")
        values = merged["valid_pixel_fraction"].dropna()
        assert ((values >= 0.0) & (values <= 1.0)).all()

    def test_ndvi_values_preserved_by_merge(self):
        merged = merge_ndvi_and_coverage(self._ndvi_raw(), self._coverage(),
                                          "parcel_01")
        assert list(merged["ndvi_mean"]) == [pytest.approx(0.6),
                                             pytest.approx(0.4)]


# ============================================================
# SECTION F: offline openEO processing-graph construction
# ============================================================

@pytest.fixture(scope="module")
def processing_config():
    return export_mod.load_config(REPO_ROOT / "backend/ml/processing_config.json")


@pytest.fixture(scope="module")
def parcel_geojson(processing_config):
    with open(
        REPO_ROOT / processing_config["parcel_geojson"], encoding="utf-8"
    ) as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def graphs(parcel_geojson, processing_config):
    """Build all three graphs offline — no authentication, no batch job."""
    import openeo

    connection = openeo.connect("https://openeo.dataspace.copernicus.eu")
    temporal_extent = [
        processing_config["time_interval"]["start"],
        processing_config["time_interval"]["end"],
    ]
    return export_mod.build_processing_graphs(
        connection, processing_config, temporal_extent, parcel_geojson
    )


def _graph_dict(cube) -> dict:
    return json.loads(cube.to_json())["process_graph"]


class TestGraphConstruction:
    def test_all_three_graphs_built(self, graphs):
        assert set(graphs) == {"ndvi", "valid", "eligible"}
        for name, cube in graphs.items():
            graph = _graph_dict(cube)
            assert graph, name
            assert any(
                isinstance(node, dict) and node.get("result")
                for node in graph.values()
            ), name

    def test_no_legacy_unsupported_operations(self, graphs):
        """The old graph used DataCube.astype, which does not exist in the
        installed openeo client; the new graphs must be buildable."""
        for name, cube in graphs.items():
            processes = _all_processes(_graph_dict(cube))
            assert "astype" not in processes, name

    def test_expected_processes_present(self, graphs):
        ndvi_processes = _all_processes(_graph_dict(graphs["ndvi"]))
        assert {
            "load_collection", "mask", "resample_cube_spatial",
            "aggregate_spatial", "reduce_dimension",
        } <= ndvi_processes
        # NDVI arithmetic survives in the graph.
        assert "subtract" in ndvi_processes
        assert "divide" in ndvi_processes
        for name in ("valid", "eligible"):
            processes = _all_processes(_graph_dict(graphs[name]))
            assert {
                "load_collection", "convert_data_type", "aggregate_spatial",
                "reduce_dimension",
            } <= processes, name

    def test_valid_graph_uses_scl_classes_4_and_5(self, graphs):
        assert _eq_constants(_graph_dict(graphs["valid"])) == {4, 5}

    def test_eligible_graph_uses_scl_classes_1_to_11(self, graphs):
        assert _eq_constants(_graph_dict(graphs["eligible"])) == set(range(1, 12))

    def test_ndvi_graph_resamples_mask_to_10m_grid(self, graphs):
        """The 20 m SCL mask must be explicitly resampled (nearest) onto the
        10 m NDVI grid instead of silently mixing resolutions."""
        nodes = _find_nodes(_graph_dict(graphs["ndvi"]), "resample_cube_spatial")
        assert nodes, "resample_cube_spatial missing from NDVI graph"
        for node in nodes:
            assert node["arguments"].get("method") == "near"

    def test_numerator_and_denominator_share_geometry(self, graphs,
                                                      parcel_geojson):
        """Both coverage graphs must aggregate over the identical parcel
        FeatureCollection, so numerator and denominator cover the same
        pixels on the same (SCL 20 m) grid."""
        valid_nodes = _find_nodes(_graph_dict(graphs["valid"]), "aggregate_spatial")
        eligible_nodes = _find_nodes(
            _graph_dict(graphs["eligible"]), "aggregate_spatial"
        )
        assert len(valid_nodes) == 1
        assert len(eligible_nodes) == 1
        valid_geometry = valid_nodes[0]["arguments"]["geometries"]
        eligible_geometry = eligible_nodes[0]["arguments"]["geometries"]
        assert valid_geometry == eligible_geometry == parcel_geojson

    def test_all_graphs_use_same_load_and_reducer(self, graphs,
                                                  processing_config):
        """Every graph loads the same collection with the same bands and
        aggregates with a mean reducer over the parcel."""
        for name, cube in graphs.items():
            graph = _graph_dict(cube)
            loads = _find_nodes(graph, "load_collection")
            assert len(loads) == 1, name
            assert loads[0]["arguments"]["id"] == processing_config["collection"]
            assert loads[0]["arguments"]["bands"] == processing_config["bands"]
            assert loads[0]["arguments"]["temporal_extent"] == [
                processing_config["time_interval"]["start"],
                processing_config["time_interval"]["end"],
            ]
            means = _find_nodes(graph, "mean")
            assert means, name
            aggregates = _find_nodes(graph, "aggregate_spatial")
            assert len(aggregates) == 1, name

    def test_graphs_serializable(self, graphs):
        for name, cube in graphs.items():
            payload = json.loads(cube.to_json())
            assert "process_graph" in payload, name
            json.dumps(payload)  # must not raise


# ============================================================
# SECTION G: config validation
# ============================================================

class TestConfigValidation:
    def test_missing_eligible_classes_is_rejected(self, tmp_path):
        config = {
            "parcel_id": "parcel_01",
            "parcel_geojson": "data/parcels/parcel_01.geojson",
            "time_interval": {"start": "2024-03-01", "end": "2024-11-01"},
            "collection": "SENTINEL2_L2A",
            "bands": ["B04", "B08", "SCL"],
            "scl_accepted_classes": [4, 5],
            # scl_eligible_classes intentionally missing
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with pytest.raises(SystemExit):
            export_mod.load_config(path)

    def test_real_config_loads(self):
        config = export_mod.load_config(
            REPO_ROOT / "backend/ml/processing_config.json"
        )
        assert config["scl_eligible_classes"] == list(range(1, 12))
        assert config["scl_accepted_classes"] == [4, 5]
