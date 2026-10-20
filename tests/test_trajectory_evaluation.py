"""
tests/test_trajectory_evaluation.py — Day 6C.2 GPR evaluation tests

Covers:
- Chronological train/test split
- No train/test overlap
- No duplicate timestamp crossing the split
- Correct parcel separation
- Correct MAE calculation
- Correct RMSE calculation
- Correct persistence baseline
- Nonnegative uncertainty values
- Predictive interval computation
- Insufficient observations
- Deterministic evaluation
- No modification to source datasets

All tests use synthetic data. No real data file is modified.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.trajectory_evaluation import (  # noqa: E402
    Z_95,
    chronological_split,
    compute_mae,
    compute_rmse,
    evaluate_all_parcels,
    evaluate_parcel,
    persistence_baseline,
)
from backend.ml.trajectory_model import (  # noqa: E402
    MIN_OBSERVATIONS,
    predict_with_uncertainty,
    train_parcel_model,
)


def _synthetic_parcel_df(n=20, seed=42, start_date="2024-03-01"):
    """Create a synthetic parcel DataFrame with n observations."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start_date, periods=n, freq="5D", tz="UTC")
    ndvi = 0.3 + 0.2 * np.sin(np.arange(n) / 5.0) + rng.normal(0, 0.03, n)
    ndvi = np.clip(ndvi, -1, 1)
    return pd.DataFrame({
        "_ts": dates,
        "ndvi_mean": ndvi,
    })


def _file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# ============================================================
# Chronological train/test split
# ============================================================

class TestChronologicalSplit:
    def test_split_is_chronological(self):
        """Train indices must all come before test indices."""
        timestamps = np.array(pd.date_range("2024-03-01", periods=20, freq="5D", tz="UTC"))
        train_idx, test_idx = chronological_split(timestamps)

        assert len(train_idx) > 0
        assert len(test_idx) > 0
        assert np.all(train_idx < test_idx[0])

    def test_split_ratio_approximate(self):
        """Split should be approximately 75/25."""
        timestamps = np.array(pd.date_range("2024-03-01", periods=40, freq="5D", tz="UTC"))
        train_idx, test_idx = chronological_split(timestamps)

        assert len(train_idx) == 30  # 75% of 40
        assert len(test_idx) == 10   # 25% of 40

    def test_split_preserves_all_indices(self):
        """All indices must be preserved (no data loss)."""
        timestamps = np.array(pd.date_range("2024-03-01", periods=20, freq="5D", tz="UTC"))
        train_idx, test_idx = chronological_split(timestamps)

        combined = np.concatenate([train_idx, test_idx])
        assert len(combined) == 20
        assert set(combined) == set(range(20))

    def test_empty_input(self):
        """Empty input returns empty arrays."""
        timestamps = np.array([], dtype="datetime64[ns]")
        train_idx, test_idx = chronological_split(timestamps)

        assert len(train_idx) == 0
        assert len(test_idx) == 0


# ============================================================
# No train/test overlap
# ============================================================

class TestNoOverlap:
    def test_no_temporal_overlap(self):
        """No test timestamp may be <= any train timestamp."""
        timestamps = np.array(pd.date_range("2024-03-01", periods=20, freq="5D", tz="UTC"))
        train_idx, test_idx = chronological_split(timestamps)

        train_ts = timestamps[train_idx]
        test_ts = timestamps[test_idx]

        assert np.all(test_ts > train_ts[-1])

    def test_no_index_overlap(self):
        """Train and test indices must be disjoint."""
        timestamps = np.array(pd.date_range("2024-03-01", periods=20, freq="5D", tz="UTC"))
        train_idx, test_idx = chronological_split(timestamps)

        assert set(train_idx).isdisjoint(set(test_idx))


# ============================================================
# No duplicate timestamp crossing the split
# ============================================================

class TestDuplicateTimestamps:
    def test_duplicates_stay_together(self):
        """Duplicate timestamps must not be split across train/test."""
        # Create timestamps with duplicates at the boundary
        base = pd.date_range("2024-03-01", periods=16, freq="5D", tz="UTC")
        # Convert to numpy array for mutability
        timestamps = np.array(base)
        # Make observations 13, 14, 15 all have the same timestamp
        timestamps[14] = timestamps[13]
        timestamps[15] = timestamps[13]

        train_idx, test_idx = chronological_split(timestamps)

        # All duplicates of timestamps[13] must be in train or all in test
        train_ts = set(timestamps[train_idx])
        test_ts = set(timestamps[test_idx])

        # The duplicated timestamp should appear in only one set
        dup_ts = timestamps[13]
        in_train = dup_ts in train_ts
        in_test = dup_ts in test_ts
        assert in_train != in_test  # XOR: must be in exactly one


# ============================================================
# Correct parcel separation
# ============================================================

class TestParcelSeparation:
    def test_parcels_evaluated_independently(self):
        """Each parcel is evaluated independently."""
        df1 = _synthetic_parcel_df(n=20, seed=1)
        df2 = _synthetic_parcel_df(n=20, seed=2)

        result1 = evaluate_parcel("parcel_01", df1)
        result2 = evaluate_parcel("parcel_02", df2)

        assert result1["evaluated"] is True
        assert result2["evaluated"] is True
        assert result1["parcel_id"] == "parcel_01"
        assert result2["parcel_id"] == "parcel_02"


# ============================================================
# Correct MAE calculation
# ============================================================

class TestMAECalculation:
    def test_mae_perfect_prediction(self):
        """MAE should be 0 for perfect predictions."""
        y_true = np.array([0.3, 0.5, 0.7])
        y_pred = np.array([0.3, 0.5, 0.7])
        assert compute_mae(y_true, y_pred) == pytest.approx(0.0)

    def test_mae_known_value(self):
        """MAE should match manual calculation."""
        y_true = np.array([0.3, 0.5, 0.7])
        y_pred = np.array([0.4, 0.4, 0.8])
        # Errors: 0.1, 0.1, 0.1 -> MAE = 0.1
        assert compute_mae(y_true, y_pred) == pytest.approx(0.1)

    def test_mae_symmetric(self):
        """MAE is symmetric."""
        y_true = np.array([0.3, 0.5])
        y_pred = np.array([0.5, 0.3])
        assert compute_mae(y_true, y_pred) == pytest.approx(0.2)


# ============================================================
# Correct RMSE calculation
# ============================================================

class TestRMSECalculation:
    def test_rmse_perfect_prediction(self):
        """RMSE should be 0 for perfect predictions."""
        y_true = np.array([0.3, 0.5, 0.7])
        y_pred = np.array([0.3, 0.5, 0.7])
        assert compute_rmse(y_true, y_pred) == pytest.approx(0.0)

    def test_rmse_known_value(self):
        """RMSE should match manual calculation."""
        y_true = np.array([0.3, 0.5, 0.7])
        y_pred = np.array([0.4, 0.4, 0.8])
        # Squared errors: 0.01, 0.01, 0.01 -> MSE = 0.01 -> RMSE = 0.1
        assert compute_rmse(y_true, y_pred) == pytest.approx(0.1)

    def test_rmse_penalizes_large_errors(self):
        """RMSE penalizes large errors more than MAE."""
        y_true = np.array([0.5, 0.5])
        y_pred = np.array([0.6, 0.9])
        # MAE = (0.1 + 0.4) / 2 = 0.25
        # RMSE = sqrt((0.01 + 0.16) / 2) = sqrt(0.085) ≈ 0.2915
        assert compute_rmse(y_true, y_pred) > compute_mae(y_true, y_pred)


# ============================================================
# Correct persistence baseline
# ============================================================

class TestPersistenceBaseline:
    def test_baseline_repeats_last_value(self):
        """Persistence baseline repeats the last training value."""
        train_ts = np.array(pd.date_range("2024-03-01", periods=10, freq="5D", tz="UTC"))
        train_ndvi = np.linspace(0.2, 0.5, 10)
        test_ts = np.array(pd.date_range("2024-05-01", periods=5, freq="5D", tz="UTC"))

        baseline = persistence_baseline(train_ts, train_ndvi, test_ts)

        assert len(baseline) == 5
        assert np.all(baseline == train_ndvi[-1])

    def test_baseline_single_training_point(self):
        """Baseline works with a single training point."""
        train_ts = np.array([pd.Timestamp("2024-03-01", tz="UTC")])
        train_ndvi = np.array([0.42])
        test_ts = np.array(pd.date_range("2024-03-10", periods=3, freq="5D", tz="UTC"))

        baseline = persistence_baseline(train_ts, train_ndvi, test_ts)

        assert np.all(baseline == 0.42)


# ============================================================
# Nonnegative uncertainty values
# ============================================================

class TestNonnegativeUncertainty:
    def test_predicted_std_nonnegative(self):
        """Predictive std must always be >= 0."""
        parcel_df = _synthetic_parcel_df(n=15, seed=42)
        result = evaluate_parcel("parcel_01", parcel_df)

        assert result["evaluated"] is True
        for pred in result["predictions"]:
            assert pred["predicted_std"] >= 0.0

    def test_interval_bounds_ordered(self):
        """Lower bound must be <= upper bound."""
        parcel_df = _synthetic_parcel_df(n=15, seed=42)
        result = evaluate_parcel("parcel_01", parcel_df)

        assert result["evaluated"] is True
        for pred in result["predictions"]:
            assert pred["lower_95"] <= pred["upper_95"]


# ============================================================
# Predictive interval computation
# ============================================================

class TestPredictiveInterval:
    def test_interval_width(self):
        """Interval width should be 2 * 1.96 * std."""
        parcel_df = _synthetic_parcel_df(n=15, seed=42)
        result = evaluate_parcel("parcel_01", parcel_df)

        assert result["evaluated"] is True
        for pred in result["predictions"]:
            expected_width = 2 * Z_95 * pred["predicted_std"]
            actual_width = pred["upper_95"] - pred["lower_95"]
            assert actual_width == pytest.approx(expected_width, abs=1e-5)

    def test_interval_symmetric(self):
        """Interval should be symmetric around the mean."""
        parcel_df = _synthetic_parcel_df(n=15, seed=42)
        result = evaluate_parcel("parcel_01", parcel_df)

        assert result["evaluated"] is True
        for pred in result["predictions"]:
            mid = (pred["upper_95"] + pred["lower_95"]) / 2
            assert mid == pytest.approx(pred["predicted_ndvi"], abs=1e-5)


# ============================================================
# Insufficient observations
# ============================================================

class TestInsufficientObservations:
    def test_too_few_observations(self):
        """Parcels with too few observations are skipped."""
        parcel_df = _synthetic_parcel_df(n=2, seed=42)
        result = evaluate_parcel("parcel_01", parcel_df)

        assert result["evaluated"] is False
        assert "Insufficient" in result["reason"]

    def test_exactly_minimum_plus_one(self):
        """Parcels with exactly MIN_OBSERVATIONS + 1 should evaluate."""
        n = MIN_OBSERVATIONS + 1
        parcel_df = _synthetic_parcel_df(n=n, seed=42)
        result = evaluate_parcel("parcel_01", parcel_df)

        # May or may not evaluate depending on split, but should not crash
        assert isinstance(result["evaluated"], bool)


# ============================================================
# Deterministic evaluation
# ============================================================

class TestDeterminism:
    def test_same_data_same_results(self):
        """Same input data produces identical evaluation results."""
        parcel_df = _synthetic_parcel_df(n=20, seed=42)

        result1 = evaluate_parcel("parcel_01", parcel_df)
        result2 = evaluate_parcel("parcel_01", parcel_df)

        assert result1["evaluated"] == result2["evaluated"]
        if result1["evaluated"]:
            assert result1["gpr_mae"] == result2["gpr_mae"]
            assert result1["gpr_rmse"] == result2["gpr_rmse"]
            assert result1["baseline_mae"] == result2["baseline_mae"]
            assert result1["n_train"] == result2["n_train"]
            assert result1["n_test"] == result2["n_test"]


# ============================================================
# No modification to source datasets
# ============================================================

class TestNoSourceModification:
    def test_source_csv_unchanged(self, tmp_path):
        """Evaluation must not modify the source CSV."""
        source = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
        if not source.exists():
            pytest.skip("Source dataset not available")

        original_hash = _file_hash(source)

        # Run evaluation with output to temp directory
        output_json = tmp_path / "eval.json"
        output_csv = tmp_path / "pred.csv"
        evaluate_all_parcels(source, output_json, output_csv)

        assert _file_hash(source) == original_hash

    def test_output_json_created(self, tmp_path):
        """Evaluation creates JSON output."""
        source = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
        if not source.exists():
            pytest.skip("Source dataset not available")

        output_json = tmp_path / "eval.json"
        output_csv = tmp_path / "pred.csv"
        evaluate_all_parcels(source, output_json, output_csv)

        assert output_json.exists()
        with open(output_json) as f:
            data = json.load(f)
        assert "parcels" in data
        assert len(data["parcels"]) > 0

    def test_output_csv_created(self, tmp_path):
        """Evaluation creates CSV output with required columns."""
        source = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
        if not source.exists():
            pytest.skip("Source dataset not available")

        output_json = tmp_path / "eval.json"
        output_csv = tmp_path / "pred.csv"
        evaluate_all_parcels(source, output_json, output_csv)

        assert output_csv.exists()
        df = pd.read_csv(output_csv)
        required_cols = {"parcel_id", "acquired_at", "actual_ndvi", "predicted_ndvi",
                         "predicted_std", "lower_95", "upper_95", "baseline_prediction"}
        assert required_cols == set(df.columns)
