"""
tests/test_trajectory_diagnostics.py — Day 6C.2A diagnostic tests

Covers:
- Fixed time origin (the root-cause property the original evaluation violated).
- Rolling-origin ordering (targets strictly after the training window).
- Persistence and linear-trend behaviour.
- GPR candidate fitting and finite predictions.
- MAE / RMSE aggregation.
- Kernel hyperparameter extraction.

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

from backend.ml.trajectory_diagnostics import (  # noqa: E402
    CANDIDATE_GPR_EXISTING,
    CANDIDATE_LINEAR,
    CANDIDATE_PERSISTENCE,
    aggregate_rolls,
    elapsed_days_from_origin,
    fitted_kernel_summary,
    predict_candidate,
    rolling_origin_validation,
)
from backend.ml.trajectory_model import (  # noqa: E402
    observations_to_training_data,
    train_parcel_model,
)


def _synthetic_train_df(n=16, seed=7):
    """Sorted training frame with a rising-then-falling NDVI curve."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-03-01", periods=n, freq="5D", tz="UTC")
    elapsed = np.arange(n, dtype=float) * 5.0
    ndvi = 0.3 + 0.4 * np.sin(elapsed / 40.0) + rng.normal(0, 0.02, n)
    ndvi = np.clip(ndvi, -1, 1)
    return pd.DataFrame({
        "parcel_id": "parcel_01",
        "_ts": dates,
        "ndvi_mean": ndvi,
    })


# ============================================================
# Time origin
# ============================================================
class TestTimeOrigin:
    def test_elapsed_days_use_fixed_origin(self):
        """Targets are measured from the training origin, never re-zeroed."""
        ts = np.array(pd.date_range("2024-03-01", periods=12, freq="5D", tz="UTC"))
        ts_ns = ts.astype("datetime64[ns]").astype(np.int64)
        origin = int(ts_ns[0])

        train_el = elapsed_days_from_origin(ts_ns[:8], origin)
        target_el = elapsed_days_from_origin(ts_ns[8:12], origin)

        assert train_el[0] == pytest.approx(0.0)
        assert train_el[-1] == pytest.approx(35.0)
        # First target is 40 days after the origin, NOT 0.
        assert target_el[0] == pytest.approx(40.0)
        assert target_el[0] > train_el[-1]

    def test_original_helper_rezeroes_test_subset(self):
        """Characterisation of the defect: the original helper re-zeroes its input.

        Calling ``observations_to_training_data`` on a test subset resets the
        origin to the subset's own minimum. This is exactly what produced the
        misaligned Day 6C.2 test features. Documented here as a regression guard
        for the diagnostic path, which must NOT do this.
        """
        ts = np.array(pd.date_range("2024-03-01", periods=12, freq="5D", tz="UTC"))
        ts_ns = ts.astype("datetime64[ns]").astype(np.int64)

        subset_elapsed, _ = observations_to_training_data(
            np.zeros(4), ts_ns[8:12]
        )
        assert subset_elapsed[0] == pytest.approx(0.0)

        fixed_elapsed = elapsed_days_from_origin(ts_ns[8:12], int(ts_ns[0]))
        assert fixed_elapsed[0] == pytest.approx(40.0)


# ============================================================
# Rolling-origin validation
# ============================================================
class TestRollingOrigin:
    def test_targets_are_strictly_after_training_window(self):
        df = _synthetic_train_df(n=16)
        rows = rolling_origin_validation(
            df,
            candidates=[CANDIDATE_PERSISTENCE],
            min_train_window=8,
            horizon=1,
        )
        assert len(rows) == 16 - 8

        sorted_times = list(df["_ts"])
        for i, row in enumerate(rows):
            target = pd.Timestamp(row["target_time"])
            # The target must be after every observation used to train.
            last_train = sorted_times[8 + i - 1]
            assert target > last_train

    def test_all_candidates_produce_finite_predictions(self):
        df = _synthetic_train_df(n=14)
        rows = rolling_origin_validation(
            df,
            candidates=[CANDIDATE_PERSISTENCE, CANDIDATE_LINEAR, CANDIDATE_GPR_EXISTING],
            min_train_window=6,
            horizon=1,
        )
        assert len(rows) == 3 * (14 - 6)
        for row in rows:
            assert np.isfinite(row["prediction"])
            assert np.isfinite(row["actual"])

    def test_horizon_validation(self):
        df = _synthetic_train_df(n=14)
        rows = rolling_origin_validation(
            df,
            candidates=[CANDIDATE_PERSISTENCE],
            min_train_window=6,
            horizon=3,
        )
        # folds = n - horizon - min_train_window + 1 = 14 - 3 - 6 + 1 = 6
        assert len(rows) == (14 - 3 - 6 + 1) * 3

    def test_invalid_horizon_raises(self):
        df = _synthetic_train_df(n=10)
        with pytest.raises(ValueError):
            rolling_origin_validation(df, min_train_window=4, horizon=0)


# ============================================================
# Candidate behaviour
# ============================================================
class TestCandidates:
    def test_persistence_repeats_last_training_value(self):
        train_elapsed = np.array([0.0, 5.0, 10.0])
        train_ndvi = np.array([0.2, 0.3, 0.25])
        mean, std = predict_candidate(
            CANDIDATE_PERSISTENCE, train_elapsed, train_ndvi, np.array([15.0])
        )
        assert mean[0] == pytest.approx(0.25)
        assert std is None

    def test_linear_trend_near_perfect_on_linear_signal(self):
        train_elapsed = np.linspace(0.0, 50.0, 10)
        train_ndvi = 0.1 + 0.02 * train_elapsed
        mean, std = predict_candidate(
            CANDIDATE_LINEAR, train_elapsed, train_ndvi, np.array([60.0])
        )
        assert mean[0] == pytest.approx(0.1 + 0.02 * 60.0, abs=1e-6)
        assert std is None

    def test_gpr_candidate_returns_std(self):
        train_elapsed = np.linspace(0.0, 100.0, 12)
        train_ndvi = 0.3 + 0.2 * np.sin(train_elapsed / 20.0)
        mean, std = predict_candidate(
            CANDIDATE_GPR_EXISTING, train_elapsed, train_ndvi, np.array([110.0])
        )
        assert np.isfinite(mean[0])
        assert std is not None
        assert std[0] >= 0.0

    def test_unknown_candidate_raises(self):
        with pytest.raises(ValueError):
            predict_candidate("nope", np.array([0.0, 1.0]), np.array([0.2, 0.3]), np.array([2.0]))


# ============================================================
# Aggregation
# ============================================================
class TestAggregation:
    def test_mae_and_rmse_known_values(self):
        rows = [
            {"parcel_id": "p", "candidate": "c", "abs_error": 1.0,
             "squared_error": 1.0, "predicted_std": np.nan, "inside_95": None},
            {"parcel_id": "p", "candidate": "c", "abs_error": 3.0,
             "squared_error": 9.0, "predicted_std": np.nan, "inside_95": None},
        ]
        out = {r["candidate"]: r for r in aggregate_rolls(rows) if r["scope"] == "__all__"}
        # MAE = 2, RMSE = sqrt((1+9)/2) = sqrt(5)
        assert out["c"]["mae"] == pytest.approx(2.0)
        assert out["c"]["rmse"] == pytest.approx(np.sqrt(5.0))

    def test_empty_rows(self):
        assert aggregate_rolls([]) == []


# ============================================================
# Kernel summary
# ============================================================
class TestKernelSummary:
    def test_extracts_hyperparameters(self):
        df = _synthetic_train_df(n=12)
        ts_ns = df["_ts"].values.astype("datetime64[ns]").astype(np.int64)
        elapsed, ndvi = observations_to_training_data(df["ndvi_mean"].values, ts_ns)
        result = train_parcel_model("parcel_01", elapsed, ndvi)
        assert result["trained"] is True

        summary = fitted_kernel_summary(result["model"])
        assert any(k.endswith("matern_length_scale") for k in summary)
        assert any(k.endswith("white_noise_level") for k in summary)
        assert "y_train_mean" in summary
        assert "y_train_std" in summary
