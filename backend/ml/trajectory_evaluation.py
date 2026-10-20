"""
backend/ml/trajectory_evaluation.py — Day 6C.2: Leakage-free chronological evaluation

Evaluates per-parcel GPR models on held-out test observations using a strict
chronological train/test split. No test data is ever used for training or
hyperparameter selection.

This module does NOT:
- modify the source dataset,
- tune hyperparameters on test data,
- substitute training-set predictions for held-out predictions,
- claim that nominal 95% intervals provide calibrated 95% coverage.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend.ml.trajectory_model import (
    MIN_OBSERVATIONS,
    observations_to_training_data,
    predict_with_uncertainty,
    train_parcel_model,
)

# Chronological split ratio
TRAIN_FRACTION = 0.75

# Minimum test observations required for meaningful evaluation
MIN_TEST_OBSERVATIONS = 1

# Z-score for nominal 95% predictive interval
Z_95 = 1.96


def chronological_split(
    timestamps: np.ndarray,
    train_fraction: float = TRAIN_FRACTION,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Split sorted timestamps chronologically into train and test indices.

    The earliest ~75% of observations form the training set; the latest ~25%
    form the test set. Duplicate timestamps are kept entirely on one side of
    the split to prevent leakage.

    Parameters
    ----------
    timestamps : np.ndarray
        Sorted array of timestamps (datetime64[ns]).
    train_fraction : float
        Fraction of observations for training (default 0.75).

    Returns
    -------
    (train_indices, test_indices) : tuple of np.ndarray
        Index arrays into the original sorted array.
    """
    n = len(timestamps)
    if n == 0:
        return np.array([], dtype=int), np.array([], dtype=int)

    # Find the split point: earliest 75% for training
    split_idx = int(np.floor(n * train_fraction))
    split_idx = max(split_idx, MIN_OBSERVATIONS)
    split_idx = min(split_idx, n - MIN_TEST_OBSERVATIONS)

    # Handle duplicate timestamps at the boundary
    if split_idx < n:
        boundary_ts = timestamps[split_idx]
        # Move split_idx back so all duplicates of boundary_ts stay in train
        while split_idx > 0 and timestamps[split_idx - 1] == boundary_ts:
            split_idx -= 1
        # If that would leave too few training observations, move forward
        if split_idx < MIN_OBSERVATIONS:
            split_idx = int(np.floor(n * train_fraction))
            while split_idx < n and timestamps[split_idx] == boundary_ts:
                split_idx += 1

    train_indices = np.arange(0, split_idx)
    test_indices = np.arange(split_idx, n)

    return train_indices, test_indices


def compute_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error."""
    return float(np.mean(np.abs(y_true - y_pred)))


def compute_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error."""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def persistence_baseline(train_timestamps: np.ndarray, train_ndvi: np.ndarray,
                         test_timestamps: np.ndarray) -> np.ndarray:
    """
    Persistence baseline: predict the last training NDVI value for all test points.

    Parameters
    ----------
    train_timestamps : np.ndarray
        Training timestamps (sorted).
    train_ndvi : np.ndarray
        Training NDVI values.
    test_timestamps : np.ndarray
        Test timestamps (sorted).

    Returns
    -------
    predictions : np.ndarray
        Last training NDVI value repeated for each test point.
    """
    last_value = train_ndvi[-1]
    return np.full(len(test_timestamps), last_value)


def evaluate_parcel(
    parcel_id: str,
    parcel_df: pd.DataFrame,
    train_fraction: float = TRAIN_FRACTION,
) -> dict[str, object]:
    """
    Evaluate a single parcel using chronological train/test split.

    Parameters
    ----------
    parcel_id : str
        Parcel identifier.
    parcel_df : pd.DataFrame
        DataFrame with columns '_ts' (datetime64[ns, UTC]) and 'ndvi_mean' (float),
        sorted chronologically.
    train_fraction : float
        Fraction for training split.

    Returns
    -------
    dict with evaluation results or skip reason.
    """
    n_obs = len(parcel_df)

    if n_obs < MIN_OBSERVATIONS + MIN_TEST_OBSERVATIONS:
        return {
            "parcel_id": parcel_id,
            "evaluated": False,
            "reason": f"Insufficient observations: {n_obs} < {MIN_OBSERVATIONS + MIN_TEST_OBSERVATIONS}",
            "n_train": 0,
            "n_test": 0,
        }

    # Sort chronologically
    parcel_df = parcel_df.sort_values("_ts").reset_index(drop=True)

    timestamps = parcel_df["_ts"].values.astype("datetime64[ns]")
    ndvi_values = parcel_df["ndvi_mean"].values.astype(float)

    # Chronological split
    train_idx, test_idx = chronological_split(timestamps, train_fraction)

    if len(train_idx) < MIN_OBSERVATIONS or len(test_idx) < MIN_TEST_OBSERVATIONS:
        return {
            "parcel_id": parcel_id,
            "evaluated": False,
            "reason": f"Split produced insufficient train ({len(train_idx)}) or test ({len(test_idx)}) observations",
            "n_train": len(train_idx),
            "n_test": len(test_idx),
        }

    # Extract train/test data
    train_ts = timestamps[train_idx]
    train_ndvi = ndvi_values[train_idx]
    test_ts = timestamps[test_idx]
    test_ndvi = ndvi_values[test_idx]

    # Single consistent time reference: the first TRAINING observation.
    #
    # Both training and test coordinates MUST be measured from this origin.
    # Previously the test subset was converted on its own, which reset its
    # origin to the first TEST observation; the fitted model was then queried at
    # early-season coordinates (elapsed days 0..k) instead of the true
    # held-out coordinates, producing meaningless predictions.
    train_origin_ns = int(train_ts.astype(np.int64).min())

    # Convert to elapsed days for GPR (same origin for train and test)
    train_elapsed, train_ndvi_clean = observations_to_training_data(
        train_ndvi, train_ts.astype(np.int64), origin_ns=train_origin_ns
    )
    test_elapsed, test_ndvi_clean = observations_to_training_data(
        test_ndvi, test_ts.astype(np.int64), origin_ns=train_origin_ns
    )

    # Train GPR on training data only
    result = train_parcel_model(parcel_id, train_elapsed, train_ndvi_clean)

    if not result["trained"]:
        return {
            "parcel_id": parcel_id,
            "evaluated": False,
            "reason": f"Training failed: {result['error']}",
            "n_train": len(train_idx),
            "n_test": len(test_idx),
        }

    # Predict on test data
    pred = predict_with_uncertainty(result["model"], test_elapsed)
    pred_mean = pred["mean"]
    pred_std = pred["std"]

    # Compute metrics
    gpr_mae = compute_mae(test_ndvi_clean, pred_mean)
    gpr_rmse = compute_rmse(test_ndvi_clean, pred_mean)

    # Persistence baseline
    baseline_pred = persistence_baseline(train_ts, train_ndvi_clean, test_ts)
    baseline_mae = compute_mae(test_ndvi_clean, baseline_pred)
    baseline_rmse = compute_rmse(test_ndvi_clean, baseline_pred)

    # Predictive interval coverage
    lower_95 = pred_mean - Z_95 * pred_std
    upper_95 = pred_mean + Z_95 * pred_std
    inside_interval = (test_ndvi_clean >= lower_95) & (test_ndvi_clean <= upper_95)
    coverage = float(np.mean(inside_interval)) if len(inside_interval) > 0 else 0.0
    mean_std = float(np.mean(pred_std))

    # Test period
    test_start = pd.Timestamp(test_ts[0]).strftime("%Y-%m-%dT%H:%M:%SZ")
    test_end = pd.Timestamp(test_ts[-1]).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "parcel_id": parcel_id,
        "evaluated": True,
        "reason": None,
        "n_train": len(train_idx),
        "n_test": len(test_idx),
        "test_period_start": test_start,
        "test_period_end": test_end,
        "gpr_mae": round(gpr_mae, 6),
        "gpr_rmse": round(gpr_rmse, 6),
        "baseline_mae": round(baseline_mae, 6),
        "baseline_rmse": round(baseline_rmse, 6),
        "gpr_better_than_baseline": bool(gpr_mae < baseline_mae),
        "predictive_interval_coverage_95": round(coverage, 4),
        "mean_predictive_std": round(mean_std, 6),
        "predictions": [
            {
                "acquired_at": pd.Timestamp(test_ts[i]).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "actual_ndvi": round(float(test_ndvi_clean[i]), 6),
                "predicted_ndvi": round(float(pred_mean[i]), 6),
                "predicted_std": round(float(pred_std[i]), 6),
                "lower_95": round(float(lower_95[i]), 6),
                "upper_95": round(float(upper_95[i]), 6),
                "baseline_prediction": round(float(baseline_pred[i]), 6),
            }
            for i in range(len(test_ts))
        ],
    }


def evaluate_all_parcels(
    input_path: Path,
    output_json: Path,
    output_csv: Path,
    train_fraction: float = TRAIN_FRACTION,
) -> dict[str, object]:
    """
    Evaluate all parcels and save results.

    Parameters
    ----------
    input_path : Path
        Path to observations CSV.
    output_json : Path
        Path for JSON output.
    output_csv : Path
        Path for CSV predictions output.
    train_fraction : float
        Fraction for training split.

    Returns
    -------
    dict with evaluation summary.
    """
    df = pd.read_csv(input_path)

    required = {"parcel_id", "acquired_at", "ndvi_mean"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    # Parse and clean
    df["_ts"] = pd.to_datetime(df["acquired_at"], errors="coerce", utc=True)
    df = df[df["_ts"].notna()].copy()
    df["_ndvi"] = pd.to_numeric(df["ndvi_mean"], errors="coerce")
    df = df[df["_ndvi"].notna()].copy()
    df = df[(df["_ndvi"] >= -1) & (df["_ndvi"] <= 1)].copy()
    df = df.sort_values(["parcel_id", "_ts"]).reset_index(drop=True)

    # Ensure _ts is datetime64[ns, UTC] for numpy compatibility
    df["_ts"] = df["_ts"].dt.tz_localize(None)

    if len(df) == 0:
        raise ValueError("No valid observations after filtering.")

    parcels = sorted(df["parcel_id"].unique())
    results = []
    all_predictions = []

    for pid in parcels:
        parcel_df = df[df["parcel_id"] == pid].copy()
        result = evaluate_parcel(pid, parcel_df, train_fraction)
        results.append(result)

        if result["evaluated"]:
            for pred in result["predictions"]:
                all_predictions.append({
                    "parcel_id": pid,
                    "acquired_at": pred["acquired_at"],
                    "actual_ndvi": pred["actual_ndvi"],
                    "predicted_ndvi": pred["predicted_ndvi"],
                    "predicted_std": pred["predicted_std"],
                    "lower_95": pred["lower_95"],
                    "upper_95": pred["upper_95"],
                    "baseline_prediction": pred["baseline_prediction"],
                })

    # Save JSON
    output_json.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_file": str(input_path),
        "train_fraction": train_fraction,
        "z_95": Z_95,
        "parcels": results,
    }
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Save CSV
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    pred_df = pd.DataFrame(all_predictions)
    pred_df.to_csv(output_csv, index=False)

    return summary
