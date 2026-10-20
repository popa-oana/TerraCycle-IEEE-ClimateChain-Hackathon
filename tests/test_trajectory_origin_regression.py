"""
tests/test_trajectory_origin_regression.py — Day 6C.2B time-origin regression tests

The Day 6C.2 chronological evaluation converted the held-out test subset into
elapsed days using the subset's own minimum as the origin. The fitted GPR was
therefore queried at early-season coordinates instead of the true held-out
coordinates, producing meaningless predictions.

These tests pin the corrected behaviour:

1. Training and prediction with different date ranges.
2. Predictions using a fixed training origin.
3. Predictions independent of test-input ordering.
4. Chronological holdout evaluation.
5. Rolling validation using consistent time coordinates.
6. No test-data leakage.
7. Reproducibility of identical predictions.
8. Unchanged parcel separation.

All tests use synthetic observations only. No real data file is modified.
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
    CANDIDATE_LINEAR,
    aggregate_rolls,
    rolling_origin_validation,
)
from backend.ml.trajectory_evaluation import (  # noqa: E402
    evaluate_all_parcels,
    evaluate_parcel,
)
from backend.ml.trajectory_model import (  # noqa: E402
    observations_to_training_data,
    predict_with_uncertainty,
    train_parcel_model,
)


def _linear_frame(n=21, step_days=5, slope=0.005, start=0.2, start_date="2024-03-01"):
    """Synthetic parcel with a perfectly linear NDVI ramp over time."""
    elapsed = np.arange(n, dtype=float) * step_days
    ts = pd.date_range(start_date, periods=n, freq=f"{step_days}D", tz="UTC")
    ndvi = start + slope * elapsed
    return pd.DataFrame({"_ts": ts, "ndvi_mean": ndvi})


def _ramp_arrays():
    """Build train/test arrays for the canonical minimal example.

    Training covers elapsed days 0..100 (21 points); the held-out test covers
    days 100..120 (5 points), measured from the SAME origin.
    """
    base = np.datetime64("2024-03-01", "ns")
    train_days = np.arange(0, 101, 5)
    test_days = np.arange(100, 121, 5)
    train_ts = base + (train_days.astype("timedelta64[D]")).astype("timedelta64[ns]")
    test_ts = base + (test_days.astype("timedelta64[D]")).astype("timedelta64[ns]")
    train_ndvi = 0.2 + 0.005 * train_days
    test_ndvi = 0.2 + 0.005 * test_days
    return train_ts, train_ndvi, test_ts, test_ndvi


# ============================================================
# 1. Training and prediction with different date ranges
# ============================================================
class TestDateRangeConversion:
    def test_origin_parameter_does_not_rezero_subset(self):
        """A held-out subset keeps absolute coordinates when an origin is given."""
        ts = pd.date_range("2024-03-01", periods=12, freq="5D", tz="UTC")
        ts_ns = ts.values.astype("datetime64[ns]").astype(np.int64)
        origin = int(ts_ns[0])

        full_el, _ = observations_to_training_data(
            np.zeros(12), ts_ns, origin_ns=origin
        )
        subset_el, _ = observations_to_training_data(
            np.zeros(4), ts_ns[8:12], origin_ns=origin
        )

        assert subset_el[0] == pytest.approx(40.0)
        assert subset_el[-1] == pytest.approx(55.0)
        np.testing.assert_allclose(subset_el, full_el[8:12])

    def test_default_origin_matches_legacy_behaviour(self):
        """Omitting the origin keeps the original (min-based) behaviour."""
        ts = pd.date_range("2024-03-01", periods=12, freq="5D", tz="UTC")
        ts_ns = ts.values.astype("datetime64[ns]").astype(np.int64)

        default_el, _ = observations_to_training_data(np.zeros(12), ts_ns)
        explicit_el, _ = observations_to_training_data(
            np.zeros(12), ts_ns, origin_ns=int(ts_ns.min())
        )

        np.testing.assert_allclose(default_el, explicit_el)
        assert default_el[0] == 0.0

    def test_training_and_prediction_different_ranges(self):
        """Test elapsed days are measured from the training origin, not re-zeroed."""
        train_ts, train_ndvi, test_ts, test_ndvi = _ramp_arrays()
        origin_ns = int(train_ts.astype(np.int64).min())

        train_el, _ = observations_to_training_data(
            train_ndvi, train_ts.astype(np.int64), origin_ns=origin_ns
        )
        test_el, _ = observations_to_training_data(
            test_ndvi, test_ts.astype(np.int64), origin_ns=origin_ns
        )

        assert train_el[0] == pytest.approx(0.0)
        assert train_el[-1] == pytest.approx(100.0)
        # Test coordinates continue the training timeline.
        assert test_el[0] == pytest.approx(100.0)
        assert test_el[-1] == pytest.approx(120.0)

        res = train_parcel_model("parcel_01", train_el, train_ndvi)
        assert res["trained"] is True
        pred = predict_with_uncertainty(res["model"], test_el)
        mae = float(np.mean(np.abs(test_ndvi - pred["mean"])))
        assert mae < 0.01

    def test_fixed_origin_beats_rezeroed_coordinates(self):
        """The re-zeroed path is demonstrably wrong; the fixed path is accurate."""
        train_ts, train_ndvi, test_ts, test_ndvi = _ramp_arrays()
        origin_ns = int(train_ts.astype(np.int64).min())

        train_el, _ = observations_to_training_data(
            train_ndvi, train_ts.astype(np.int64), origin_ns=origin_ns
        )
        fixed_el, _ = observations_to_training_data(
            test_ndvi, test_ts.astype(np.int64), origin_ns=origin_ns
        )
        buggy_el, _ = observations_to_training_data(
            test_ndvi, test_ts.astype(np.int64)
        )

        # The legacy path resets the origin to the test subset minimum.
        assert buggy_el[0] == pytest.approx(0.0)

        res = train_parcel_model("parcel_01", train_el, train_ndvi)
        pred_fixed = predict_with_uncertainty(res["model"], fixed_el)
        pred_buggy = predict_with_uncertainty(res["model"], buggy_el)

        mae_fixed = float(np.mean(np.abs(test_ndvi - pred_fixed["mean"])))
        mae_buggy = float(np.mean(np.abs(test_ndvi - pred_buggy["mean"])))
        assert mae_fixed < mae_buggy / 10.0
        assert mae_fixed < 0.01


# ============================================================
# 2. Predictions using a fixed training origin
# ============================================================
class TestFixedOriginPredictions:
    def test_same_absolute_day_same_prediction(self):
        """The same absolute day yields the same prediction regardless of subset."""
        train_ts, train_ndvi, _, _ = _ramp_arrays()
        origin_ns = int(train_ts.astype(np.int64).min())
        train_el, _ = observations_to_training_data(
            train_ndvi, train_ts.astype(np.int64), origin_ns=origin_ns
        )
        res = train_parcel_model("parcel_01", train_el, train_ndvi)

        base = np.datetime64("2024-03-01", "ns")
        single_ts = base + np.timedelta64(115, "D").astype("timedelta64[ns]")
        multi_ts = base + np.array([110, 115, 120], dtype="timedelta64[D]").astype("timedelta64[ns]")

        single_el, _ = observations_to_training_data(
            np.zeros(1), np.array([single_ts]).astype(np.int64), origin_ns=origin_ns
        )
        multi_el, _ = observations_to_training_data(
            np.zeros(3), multi_ts.astype(np.int64), origin_ns=origin_ns
        )

        assert single_el[0] == pytest.approx(115.0)
        assert multi_el[1] == pytest.approx(115.0)

        p_single = predict_with_uncertainty(res["model"], single_el)
        p_multi = predict_with_uncertainty(res["model"], multi_el)
        assert p_single["mean"][0] == pytest.approx(p_multi["mean"][1])
        assert p_single["std"][0] == pytest.approx(p_multi["std"][1])

    def test_future_observations_do_not_shift_training_origin(self):
        """Test coordinates use the first TRAINING timestamp, not a shifted origin."""
        df = _linear_frame(n=20)
        ts = df["_ts"].values.astype("datetime64[ns]")
        train_ts, test_ts = ts[:15], ts[15:]
        train_origin = int(train_ts.astype(np.int64).min())

        test_el, _ = observations_to_training_data(
            df["ndvi_mean"].values[15:], test_ts.astype(np.int64), origin_ns=train_origin
        )
        # First test point is 75 days after the training origin (not 0).
        assert test_el[0] == pytest.approx(75.0)
        assert test_el[0] > 0.0


# ============================================================
# 3. Predictions independent of test-input ordering
# ============================================================
class TestOrderingIndependence:
    def test_predictions_follow_elementwise_mapping(self):
        train_ts, train_ndvi, _, _ = _ramp_arrays()
        origin_ns = int(train_ts.astype(np.int64).min())
        train_el, _ = observations_to_training_data(
            train_ndvi, train_ts.astype(np.int64), origin_ns=origin_ns
        )
        res = train_parcel_model("parcel_01", train_el, train_ndvi)

        xs = np.array([105.0, 110.0, 115.0, 120.0])
        order = [2, 0, 3, 1]

        p_sorted = predict_with_uncertainty(res["model"], xs)
        p_shuffled = predict_with_uncertainty(res["model"], xs[order])

        np.testing.assert_allclose(p_sorted["mean"][order], p_shuffled["mean"])
        np.testing.assert_allclose(p_sorted["std"][order], p_shuffled["std"])


# ============================================================
# 4. Chronological holdout evaluation
# ============================================================
class TestChronologicalHoldout:
    def test_evaluate_parcel_uses_training_origin(self):
        """evaluate_parcel predictions match a manual fixed-origin prediction."""
        df = _linear_frame(n=20)
        result = evaluate_parcel("parcel_01", df)

        assert result["evaluated"] is True
        assert result["n_train"] == 15
        assert result["n_test"] == 5

        # Reconstruct the corrected evaluation independently.
        sorted_df = df.sort_values("_ts").reset_index(drop=True)
        ts = sorted_df["_ts"].values.astype("datetime64[ns]")
        ndvi = sorted_df["ndvi_mean"].values.astype(float)
        split_idx = int(np.floor(len(ts) * 0.75))

        train_ts, test_ts = ts[:split_idx], ts[split_idx:]
        origin_ns = int(train_ts.astype(np.int64).min())
        train_el, _ = observations_to_training_data(
            ndvi[:split_idx], train_ts.astype(np.int64), origin_ns=origin_ns
        )
        test_el, _ = observations_to_training_data(
            ndvi[split_idx:], test_ts.astype(np.int64), origin_ns=origin_ns
        )

        res = train_parcel_model("parcel_01", train_el, ndvi[:split_idx])
        pred = predict_with_uncertainty(res["model"], test_el)

        assert len(result["predictions"]) == len(test_el)
        for i, p in enumerate(result["predictions"]):
            # evaluate_parcel stores values rounded to 6 decimals.
            assert round(float(pred["mean"][i]), 6) == p["predicted_ndvi"]
            assert round(float(pred["std"][i]), 6) == p["predicted_std"]

    def test_holdout_gpr_beats_persistence_on_ramp(self):
        """With a consistent origin the GP recovers the trend; persistence lags."""
        df = _linear_frame(n=21)
        result = evaluate_parcel("parcel_01", df)

        assert result["evaluated"] is True
        assert result["gpr_mae"] < 0.02
        # On a rising ramp the last training value is below all test values.
        assert result["baseline_mae"] > result["gpr_mae"]


# ============================================================
# 5. Rolling validation using consistent time coordinates
# ============================================================
class TestRollingValidation:
    def test_rolling_coordinates_are_consistent(self):
        """A linear signal must be predicted almost perfectly by linear trend."""
        df = _linear_frame(n=20)
        rows = rolling_origin_validation(
            df, candidates=[CANDIDATE_LINEAR], min_train_window=6, horizon=1
        )
        summary = {
            s["candidate"]: s
            for s in aggregate_rolls(rows)
            if s["scope"] == "__all__"
        }
        assert summary[CANDIDATE_LINEAR]["mae"] < 1e-6

    def test_rolling_targets_are_strictly_after_training_window(self):
        df = _linear_frame(n=16)
        rows = rolling_origin_validation(
            df, candidates=[CANDIDATE_LINEAR], min_train_window=8, horizon=1
        )
        sorted_times = list(df["_ts"])
        for i, row in enumerate(rows):
            target = pd.Timestamp(row["target_time"])
            assert target > sorted_times[8 + i - 1]


# ============================================================
# 6. No test-data leakage
# ============================================================
class TestNoLeakage:
    def test_test_values_do_not_change_predictions(self):
        """Modifying held-out targets must not change model predictions."""
        df = _linear_frame(n=20)
        result_before = evaluate_parcel("parcel_01", df.copy())

        modified = df.copy()
        test_start = result_before["n_train"]
        modified.iloc[test_start:, modified.columns.get_loc("ndvi_mean")] += 0.5
        result_after = evaluate_parcel("parcel_01", modified)

        assert result_after["n_train"] == result_before["n_train"]
        assert result_after["n_test"] == result_before["n_test"]
        for p_before, p_after in zip(result_before["predictions"], result_after["predictions"]):
            assert p_before["predicted_ndvi"] == p_after["predicted_ndvi"]
            assert p_before["predicted_std"] == p_after["predicted_std"]


# ============================================================
# 7. Reproducibility
# ============================================================
class TestReproducibility:
    def test_identical_evaluation_is_reproducible(self):
        df = _linear_frame(n=20)
        r1 = evaluate_parcel("parcel_01", df)
        r2 = evaluate_parcel("parcel_01", df)

        assert r1["predictions"] == r2["predictions"]
        assert r1["gpr_mae"] == r2["gpr_mae"]
        assert r1["baseline_mae"] == r2["baseline_mae"]

    def test_identical_conversion_is_deterministic(self):
        ts = pd.date_range("2024-03-01", periods=10, freq="5D", tz="UTC")
        ts_ns = ts.values.astype("datetime64[ns]").astype(np.int64)
        e1, _ = observations_to_training_data(np.zeros(10), ts_ns)
        e2, _ = observations_to_training_data(np.zeros(10), ts_ns)
        np.testing.assert_allclose(e1, e2)


# ============================================================
# 8. Unchanged parcel separation
# ============================================================
class TestParcelSeparation:
    def test_parcels_evaluated_independently(self, tmp_path):
        df1 = _linear_frame(n=20, slope=0.005, start=0.2)
        df2 = _linear_frame(n=20, slope=0.008, start=0.1)

        r1 = evaluate_parcel("parcel_01", df1)
        r2 = evaluate_parcel("parcel_02", df2)

        combined = pd.concat(
            [
                df1.assign(parcel_id="parcel_01"),
                df2.assign(parcel_id="parcel_02"),
            ],
            ignore_index=True,
        )
        combined["acquired_at"] = combined["_ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        csv_path = tmp_path / "two_parcels.csv"
        combined[["parcel_id", "acquired_at", "ndvi_mean"]].to_csv(csv_path, index=False)

        summary = evaluate_all_parcels(
            csv_path, tmp_path / "e.json", tmp_path / "p.csv"
        )
        by_id = {p["parcel_id"]: p for p in summary["parcels"]}

        assert by_id["parcel_01"]["gpr_mae"] == r1["gpr_mae"]
        assert by_id["parcel_02"]["gpr_mae"] == r2["gpr_mae"]
        np.testing.assert_allclose(
            [p["predicted_ndvi"] for p in by_id["parcel_01"]["predictions"]],
            [p["predicted_ndvi"] for p in r1["predictions"]],
        )
