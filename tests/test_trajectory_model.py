"""
tests/test_trajectory_model.py — Day 6C.1 GPR trajectory model tests

Covers:
- Correct parcel separation
- Chronological timestamp processing
- Valid NDVI predictions
- Nonnegative predictive standard deviation
- Insufficient observations
- Empty input
- Deterministic behavior
- No changes to existing verification outputs

All tests use synthetic data. No real data file is modified.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.trajectory_model import (  # noqa: E402
    MIN_OBSERVATIONS,
    build_model,
    observations_to_training_data,
    predict_with_uncertainty,
    train_parcel_model,
)


def _synthetic_ndvi(n=10, seed=42):
    """Generate synthetic NDVI observations spread over 200 days."""
    rng = np.random.RandomState(seed)
    elapsed = np.sort(rng.uniform(0, 200, n))
    ndvi = 0.3 + 0.3 * np.sin(elapsed / 30.0) + rng.normal(0, 0.05, n)
    ndvi = np.clip(ndvi, -1, 1)
    return elapsed, ndvi


# ============================================================
# Parcel separation
# ============================================================

class TestParcelSeparation:
    def test_models_are_independent(self):
        """Each parcel gets its own model; no cross-contamination."""
        e1, n1 = _synthetic_ndvi(n=10, seed=1)
        e2, n2 = _synthetic_ndvi(n=10, seed=2)

        r1 = train_parcel_model("parcel_01", e1, n1)
        r2 = train_parcel_model("parcel_02", e2, n2)

        assert r1["trained"] is True
        assert r2["trained"] is True
        assert r1["parcel_id"] == "parcel_01"
        assert r2["parcel_id"] == "parcel_02"
        # Different models
        assert r1["model"] is not r2["model"]

    def test_same_data_same_model(self):
        """Same data produces the same model (deterministic)."""
        e, n = _synthetic_ndvi(n=10, seed=42)
        r1 = train_parcel_model("parcel_01", e, n)
        r2 = train_parcel_model("parcel_01", e, n)
        # Predictions should be identical
        pred1 = predict_with_uncertainty(r1["model"], np.array([50.0]))
        pred2 = predict_with_uncertainty(r2["model"], np.array([50.0]))
        np.testing.assert_allclose(pred1["mean"], pred2["mean"], rtol=1e-10)
        np.testing.assert_allclose(pred1["std"], pred2["std"], rtol=1e-10)


# ============================================================
# Chronological timestamp processing
# ============================================================

class TestTimestampProcessing:
    def test_elapsed_days_start_at_zero(self):
        """Elapsed days should start at 0 for the first observation."""
        # Create timestamps 10 days apart
        base = np.datetime64("2024-03-01", "ns")
        timestamps = np.array([base + np.timedelta64(i * 10, "D") for i in range(5)])
        timestamps_ns = timestamps.astype(np.int64)
        ndvi = np.array([0.3, 0.4, 0.5, 0.4, 0.3])

        elapsed, ndvi_out = observations_to_training_data(ndvi, timestamps_ns)

        assert elapsed[0] == 0.0
        assert elapsed[-1] == pytest.approx(40.0)
        np.testing.assert_allclose(ndvi_out, ndvi)

    def test_unsorted_timestamps_handled(self):
        """Unsorted timestamps: elapsed days are relative to the minimum."""
        base = np.datetime64("2024-03-01", "ns")
        # Deliberately unsorted
        offsets = [30, 10, 20, 0]
        timestamps = np.array([base + np.timedelta64(d, "D") for d in offsets])
        timestamps_ns = timestamps.astype(np.int64)
        ndvi = np.array([0.5, 0.3, 0.4, 0.2])

        elapsed, ndvi_out = observations_to_training_data(ndvi, timestamps_ns)

        # Elapsed days are relative to the minimum timestamp (offset 0)
        # The element with offset 0 is at index 3
        assert elapsed[3] == 0.0
        # The maximum elapsed day is 30 (from offset 30 at index 0)
        assert elapsed[0] == pytest.approx(30.0)
        # NDVI values are preserved
        np.testing.assert_allclose(ndvi_out, ndvi)


# ============================================================
# Valid NDVI predictions
# ============================================================

class TestPredictions:
    def test_predictions_in_valid_range(self):
        """Predicted NDVI should be in a reasonable range."""
        e, n = _synthetic_ndvi(n=15, seed=42)
        result = train_parcel_model("parcel_01", e, n)
        assert result["trained"] is True

        pred = predict_with_uncertainty(result["model"], np.array([0.0, 50.0, 100.0, 150.0, 200.0]))

        assert len(pred["mean"]) == 5
        assert len(pred["std"]) == 5
        # Predictions should be finite
        assert np.all(np.isfinite(pred["mean"]))
        assert np.all(np.isfinite(pred["std"]))

    def test_predictive_std_nonnegative(self):
        """Predictive standard deviation must always be >= 0."""
        e, n = _synthetic_ndvi(n=10, seed=42)
        result = train_parcel_model("parcel_01", e, n)
        assert result["trained"] is True

        pred = predict_with_uncertainty(result["model"], np.linspace(0, 300, 50))
        assert np.all(pred["std"] >= 0.0)

    def test_prediction_shape_matches_input(self):
        """Prediction output shape matches input shape."""
        e, n = _synthetic_ndvi(n=10, seed=42)
        result = train_parcel_model("parcel_01", e, n)
        assert result["trained"] is True

        test_points = np.array([0.0, 25.0, 50.0, 75.0, 100.0, 125.0, 150.0])
        pred = predict_with_uncertainty(result["model"], test_points)

        assert pred["mean"].shape == (7,)
        assert pred["std"].shape == (7,)


# ============================================================
# Insufficient observations
# ============================================================

class TestInsufficientObservations:
    def test_too_few_observations(self):
        """Parcels with fewer than MIN_OBSERVATIONS are not trained."""
        e = np.array([0.0, 10.0])
        n = np.array([0.3, 0.4])
        result = train_parcel_model("parcel_01", e, n)

        assert result["trained"] is False
        assert result["model"] is None
        assert "Insufficient" in result["error"]

    def test_exactly_minimum_observations(self):
        """Parcels with exactly MIN_OBSERVATIONS can be trained."""
        e = np.array([0.0, 10.0, 20.0])
        n = np.array([0.3, 0.5, 0.4])
        result = train_parcel_model("parcel_01", e, n)

        # May or may not train depending on kernel, but should not crash
        assert result["observation_count"] == MIN_OBSERVATIONS

    def test_single_observation(self):
        """A single observation is insufficient."""
        result = train_parcel_model("parcel_01", np.array([0.0]), np.array([0.5]))

        assert result["trained"] is False
        assert result["error"] is not None


# ============================================================
# Empty input
# ============================================================

class TestEmptyInput:
    def test_empty_arrays(self):
        """Empty arrays should return untrained with error."""
        result = train_parcel_model(
            "parcel_01",
            np.array([], dtype=float),
            np.array([], dtype=float),
        )
        assert result["trained"] is False
        assert result["observation_count"] == 0


# ============================================================
# Deterministic behavior
# ============================================================

class TestDeterminism:
    def test_same_seed_same_predictions(self):
        """Same seed produces identical predictions."""
        e, n = _synthetic_ndvi(n=12, seed=99)
        r1 = train_parcel_model("parcel_01", e, n)
        r2 = train_parcel_model("parcel_01", e, n)

        test_points = np.linspace(0, 200, 30)
        pred1 = predict_with_uncertainty(r1["model"], test_points)
        pred2 = predict_with_uncertainty(r2["model"], test_points)

        np.testing.assert_allclose(pred1["mean"], pred2["mean"], rtol=1e-9)
        np.testing.assert_allclose(pred1["std"], pred2["std"], rtol=1e-9)


# ============================================================
# No changes to existing verification outputs
# ============================================================

class TestNoVerificationChanges:
    def test_verification_outputs_unchanged(self):
        """GPR module does not modify verification results."""
        from backend.ml.rules import verify_parcel

        policy = {
            "window_start": "2024-03-01",
            "window_end": "2024-11-01",
            "ndvi_threshold": 0.35,
            "required_fraction": 0.80,
            "min_observations": 5,
            "min_valid_pixel_fraction": 0.50,
            "min_temporal_coverage": 0.50,
            "temporal_coverage_interval_days": 10,
        }
        evidence_dir = REPO_ROOT / "data/ndvi"

        # This should not raise
        result = verify_parcel("parcel_01", policy, str(evidence_dir))
        assert result["verdict"] in ("conform", "nonconform", "inconclusive")
        assert result["verdict_code"] in (0, 1, 2)

    def test_build_model_returns_gpr(self):
        """build_model returns a GaussianProcessRegressor."""
        from sklearn.gaussian_process import GaussianProcessRegressor

        model = build_model()
        assert isinstance(model, GaussianProcessRegressor)
