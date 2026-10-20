"""
backend/ml/short_horizon.py — Rolling short-horizon NDVI forecasting evaluation

Day 6C.4 for TerraCycle Proof. Evaluates whether existing ML models provide
useful short-term NDVI predictions (next satellite acquisition) using an
expanding-window backtesting approach.

This is an EXPERIMENTAL diagnostic module. It does NOT:
- create compliance labels,
- predict compliance verdicts,
- claim validated forecasting performance,
- interpolate missing dates or invent measurements,
- modify satellite data or existing compliance results.

Each parcel's history is evaluated independently. Models are retrained at each
step using only observations available before the prediction date.
"""

from __future__ import annotations

import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from backend.ml.trajectory_model import (
    MIN_OBSERVATIONS,
    build_model,
    observations_to_training_data,
    predict_with_uncertainty,
    train_parcel_model,
)


# ---------------------------------------------------------------------------
# Baseline predictors
# ---------------------------------------------------------------------------

def predict_persistence(
    train_elapsed: np.ndarray,
    train_ndvi: np.ndarray,
    target_elapsed: np.ndarray,
) -> np.ndarray:
    """
    Persistence baseline: predict the last observed NDVI value.

    Parameters
    ----------
    train_elapsed : np.ndarray, shape (n,)
        Elapsed days for training observations.
    train_ndvi : np.ndarray, shape (n,)
        NDVI values for training observations.
    target_elapsed : np.ndarray, shape (m,)
        Elapsed days for target predictions (unused, for interface compatibility).

    Returns
    -------
    np.ndarray, shape (m,)
        Last training NDVI value repeated.
    """
    return np.full(len(target_elapsed), float(train_ndvi[-1]))


def predict_linear_trend(
    train_elapsed: np.ndarray,
    train_ndvi: np.ndarray,
    target_elapsed: np.ndarray,
    window: int | None = None,
) -> np.ndarray:
    """
    Linear trend baseline: fit OLS on trailing window of training data.

    Parameters
    ----------
    train_elapsed : np.ndarray, shape (n,)
        Elapsed days for training observations.
    train_ndvi : np.ndarray, shape (n,)
        NDVI values for training observations.
    target_elapsed : np.ndarray, shape (m,)
        Elapsed days for target predictions.
    window : int, optional
        Number of most recent observations to use for trend fitting.
        If None, uses all available training observations.

    Returns
    -------
    np.ndarray, shape (m,)
        Linear trend predictions at target_elapsed.
    """
    if window is not None and window < len(train_elapsed):
        x = train_elapsed[-window:]
        y = train_ndvi[-window:]
    else:
        x = train_elapsed
        y = train_ndvi

    # Need at least 2 points for a linear fit
    if len(x) < 2:
        return np.full(len(target_elapsed), float(train_ndvi[-1]))

    coef = np.polyfit(x, y, deg=1)
    return np.polyval(coef, target_elapsed)


def predict_gpr(
    train_elapsed: np.ndarray,
    train_ndvi: np.ndarray,
    target_elapsed: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Gaussian Process Regression prediction with uncertainty.

    Parameters
    ----------
    train_elapsed : np.ndarray, shape (n,)
        Elapsed days for training observations.
    train_ndvi : np.ndarray, shape (n,)
        NDVI values for training observations.
    target_elapsed : np.ndarray, shape (m,)
        Elapsed days for target predictions (same origin as training).

    Returns
    -------
    (mean, std) : tuple of np.ndarray
        Predicted NDVI means and predictive standard deviations.
        Returns (persistence, None) if training fails.
    """
    result = train_parcel_model("short_horizon", train_elapsed, train_ndvi)
    if not result["trained"]:
        # Fall back to persistence if GPR fails
        return predict_persistence(train_elapsed, train_ndvi, target_elapsed), None

    pred = predict_with_uncertainty(result["model"], target_elapsed)
    return pred["mean"], pred["std"]


# ---------------------------------------------------------------------------
# Core evaluation logic
# ---------------------------------------------------------------------------

HORIZON_BANDS = [
    (0, 7, "0-7_days"),
    (8, 14, "8-14_days"),
    (15, None, "15+_days"),
]

MIN_HISTORY = 8  # Minimum observations before first prediction


def evaluate_parcel_short_horizon(
    parcel_id: str,
    parcel_df: pd.DataFrame,
    min_history: int = MIN_HISTORY,
    linear_window: int | None = None,
) -> dict[str, object]:
    """
    Rolling short-horizon evaluation for a single parcel.

    For each step k from min_history to n-1:
    - Train on observations [0, k)
    - Predict observation k (the next genuine acquisition)
    - Record actual time gap in days
    - Advance window

    Parameters
    ----------
    parcel_id : str
        Parcel identifier.
    parcel_df : pd.DataFrame
        DataFrame with columns 'acquired_at' (datetime64[ns, UTC]) and
        'ndvi_mean' (float), sorted chronologically.
    min_history : int
        Minimum number of historical observations before first prediction.
    linear_window : int, optional
        Trailing window size for linear trend baseline. If None, uses all history.

    Returns
    -------
    dict with:
        parcel_id : str
        predictions : list[dict]
            Per-prediction records.
        metrics : dict
            Aggregated metrics per model and horizon band.
    """
    n = len(parcel_df)
    if n <= min_history:
        return {
            "parcel_id": parcel_id,
            "evaluated": False,
            "reason": f"Insufficient observations: {n} <= {min_history}",
            "n_observations": n,
            "min_history_required": min_history,
            "predictions": [],
            "metrics": {},
        }

    # Ensure sorted
    df = parcel_df.sort_values("acquired_at").reset_index(drop=True)
    timestamps = df["acquired_at"].values
    ndvi_values = df["ndvi_mean"].values.astype(float)

    predictions = []

    for k in range(min_history, n):
        # Training data: observations [0, k)
        train_ts = timestamps[:k]
        train_ndvi = ndvi_values[:k]

        # Target: observation k (next genuine acquisition)
        target_ts = timestamps[k:k+1]
        target_ndvi = ndvi_values[k:k+1]

        # Time origin = first training observation
        origin_ns = int(pd.Timestamp(train_ts[0]).value)  # nanoseconds since epoch

        # Convert to elapsed days (same origin for train and target)
        train_ts_ns = pd.to_datetime(train_ts).astype(np.int64).to_numpy()
        target_ts_ns = pd.to_datetime(target_ts).astype(np.int64).to_numpy()

        train_elapsed, train_ndvi_clean = observations_to_training_data(
            train_ndvi, train_ts_ns, origin_ns=origin_ns
        )
        target_elapsed, _ = observations_to_training_data(
            target_ndvi, target_ts_ns, origin_ns=origin_ns
        )

        # Actual horizon in days
        horizon_days = float(target_elapsed[0] - train_elapsed[-1])

        # Persistence prediction
        pers_pred = predict_persistence(train_elapsed, train_ndvi_clean, target_elapsed)

        # Linear trend prediction
        linear_pred = predict_linear_trend(
            train_elapsed, train_ndvi_clean, target_elapsed, window=linear_window
        )

        # GPR prediction
        gpr_mean, gpr_std = predict_gpr(train_elapsed, train_ndvi_clean, target_elapsed)

        actual = float(target_ndvi[0])

        predictions.append({
            "parcel_id": parcel_id,
            "prediction_index": k,
            "prediction_time": pd.Timestamp(target_ts[0]).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "horizon_days": round(horizon_days, 2),
            "history_size": k,
            "actual_ndvi": round(actual, 6),
            "persistence_prediction": round(float(pers_pred[0]), 6),
            "linear_trend_prediction": round(float(linear_pred[0]), 6),
            "gpr_prediction": round(float(gpr_mean[0]), 6),
            "gpr_predicted_std": round(float(gpr_std[0]), 6) if gpr_std is not None else None,
            "persistence_abs_error": round(abs(actual - pers_pred[0]), 6),
            "linear_trend_abs_error": round(abs(actual - linear_pred[0]), 6),
            "gpr_abs_error": round(abs(actual - gpr_mean[0]), 6),
        })

    # Aggregate metrics
    metrics = aggregate_metrics(predictions)

    return {
        "parcel_id": parcel_id,
        "evaluated": True,
        "reason": None,
        "n_observations": n,
        "min_history": min_history,
        "linear_window": linear_window,
        "n_predictions": len(predictions),
        "predictions": predictions,
        "metrics": metrics,
    }


def aggregate_metrics(predictions: list[dict]) -> dict[str, object]:
    """
    Aggregate per-prediction metrics by model and horizon band.

    Parameters
    ----------
    predictions : list[dict]
        Output from evaluate_parcel_short_horizon['predictions'].

    Returns
    -------
    dict with metrics per model and horizon band.
    """
    if not predictions:
        return {}

    df = pd.DataFrame(predictions)

    models = [
        ("persistence", "persistence_abs_error"),
        ("linear_trend", "linear_trend_abs_error"),
        ("gpr", "gpr_abs_error"),
    ]

    results: dict[str, object] = {
        "overall": {},
        "by_horizon_band": {},
    }

    # Overall metrics
    for model_name, error_col in models:
        errors = df[error_col].to_numpy(dtype=float)
        results["overall"][model_name] = {
            "n": int(len(errors)),
            "mae": round(float(np.mean(errors)), 6),
            "rmse": round(float(np.sqrt(np.mean(errors**2))), 6),
            "median_ae": round(float(np.median(errors)), 6),
        }

    # Metrics by horizon band
    for min_h, max_h, band_name in HORIZON_BANDS:
        mask = df["horizon_days"] >= min_h
        if max_h is not None:
            mask = mask & (df["horizon_days"] <= max_h)

        band_df = df[mask]
        n_band = len(band_df)

        band_results = {"n": int(n_band), "models": {}}

        for model_name, error_col in models:
            if n_band == 0:
                band_results["models"][model_name] = {
                    "n": 0,
                    "mae": None,
                    "rmse": None,
                    "median_ae": None,
                    "status": "insufficient_data",
                }
                continue

            errors = band_df[error_col].to_numpy(dtype=float)
            band_results["models"][model_name] = {
                "n": int(n_band),
                "mae": round(float(np.mean(errors)), 6),
                "rmse": round(float(np.sqrt(np.mean(errors**2))), 6),
                "median_ae": round(float(np.median(errors)), 6),
            }

        # GPR uncertainty calibration for this band
        gpr_std = band_df["gpr_predicted_std"].dropna()
        if len(gpr_std) > 0:
            # Check if uncertainty increases with horizon
            band_results["gpr_uncertainty"] = {
                "mean_predicted_std": round(float(np.mean(gpr_std)), 6),
                "median_predicted_std": round(float(np.median(gpr_std)), 6),
            }
        else:
            band_results["gpr_uncertainty"] = {
                "mean_predicted_std": None,
                "median_predicted_std": None,
            }

        # Nominal 95% interval coverage
        if "gpr_abs_error" in band_df.columns and "gpr_predicted_std" in band_df.columns:
            gpr_rows = band_df.dropna(subset=["gpr_predicted_std"])
            if len(gpr_rows) > 0:
                inside = np.abs(gpr_rows["actual_ndvi"] - gpr_rows["gpr_prediction"]) <= 1.96 * gpr_rows["gpr_predicted_std"]
                band_results["gpr_interval_coverage_95"] = {
                    "n": int(len(gpr_rows)),
                    "coverage": round(float(np.mean(inside)), 4),
                }
            else:
                band_results["gpr_interval_coverage_95"] = {"n": 0, "coverage": None}
        else:
            band_results["gpr_interval_coverage_95"] = {"n": 0, "coverage": None}

        results["by_horizon_band"][band_name] = band_results

    return results


def evaluate_all_parcels_short_horizon(
    input_path: Path,
    output_json: Path,
    min_history: int = MIN_HISTORY,
    linear_window: int | None = None,
) -> dict[str, object]:
    """
    Evaluate short-horizon forecasting for all parcels.

    Parameters
    ----------
    input_path : Path
        Path to observations CSV (must have parcel_id, acquired_at, ndvi_mean).
    output_json : Path
        Path for JSON output.
    min_history : int
        Minimum observations before first prediction.
    linear_window : int, optional
        Trailing window for linear trend baseline.

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
    df["acquired_at"] = pd.to_datetime(df["acquired_at"], errors="coerce", utc=True)
    df = df[df["acquired_at"].notna()].copy()
    df["ndvi_mean"] = pd.to_numeric(df["ndvi_mean"], errors="coerce")
    df = df[df["ndvi_mean"].notna()].copy()
    df = df[(df["ndvi_mean"] >= -1) & (df["ndvi_mean"] <= 1)].copy()
    df = df.sort_values(["parcel_id", "acquired_at"]).reset_index(drop=True)

    if len(df) == 0:
        raise ValueError("No valid observations after filtering.")

    parcels = sorted(df["parcel_id"].unique())
    results = []

    for pid in parcels:
        parcel_df = df[df["parcel_id"] == pid].copy()
        result = evaluate_parcel_short_horizon(
            pid, parcel_df, min_history=min_history, linear_window=linear_window
        )
        # Add presentation recommendation
        result["presentation"] = get_presentation_recommendation(result)
        results.append(result)

    # Save JSON
    output_json.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_file": str(input_path),
        "min_history": min_history,
        "linear_window": linear_window,
        "horizon_bands": HORIZON_BANDS,
        "note": "EXPERIMENTAL rolling short-horizon backtest on previously inspected data. Not a fresh independent benchmark.",
        "disclaimer": "These predictions describe NDVI forecasting only. They do not establish agronomic compliance, certification, or blockchain settlement eligibility.",
        "parcels": results,
    }
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


# ---------------------------------------------------------------------------
# Uncertainty diagnostics
# ---------------------------------------------------------------------------

def check_uncertainty_horizon_correlation(
    predictions: list[dict],
) -> dict[str, object]:
    """
    Check whether GPR predictive uncertainty correlates with prediction horizon.

    Parameters
    ----------
    predictions : list[dict]
        Predictions from evaluate_parcel_short_horizon.

    Returns
    -------
    dict with correlation statistics.
    """
    df = pd.DataFrame(predictions)
    valid = df.dropna(subset=["gpr_predicted_std", "horizon_days"])

    if len(valid) < 3:
        return {
            "n": len(valid),
            "spearman_rho": None,
            "p_value": None,
            "note": "Insufficient data for correlation test",
        }

    from scipy.stats import spearmanr

    rho, p = spearmanr(valid["horizon_days"], valid["gpr_predicted_std"])

    return {
        "n": int(len(valid)),
        "spearman_rho": round(float(rho), 4),
        "p_value": round(float(p), 4) if not np.isnan(p) else None,
        "note": "Positive rho indicates uncertainty increases with horizon",
    }


# ---------------------------------------------------------------------------
# Safe presentation helpers
# ---------------------------------------------------------------------------

def get_presentation_recommendation(parcel_results: dict) -> dict[str, object]:
    """
    Determine safe presentation behavior for a parcel's short-horizon results.

    Returns a recommendation on whether to display predictions and which model
    to prefer, based on data sufficiency and comparative performance.
    """
    if not parcel_results.get("evaluated", False):
        return {
            "display": False,
            "reason": parcel_results.get("reason", "Not evaluated"),
            "recommended_model": None,
        }

    overall = parcel_results.get("metrics", {}).get("overall", {})
    n_preds = parcel_results.get("n_predictions", 0)

    if n_preds == 0:
        return {
            "display": False,
            "reason": "No predictions generated",
            "recommended_model": None,
        }

    # Compare MAE across models
    maes = {}
    for model in ["persistence", "linear_trend", "gpr"]:
        if model in overall:
            maes[model] = overall[model].get("mae")

    if not maes:
        return {
            "display": True,
            "reason": "Predictions available but no metrics computed",
            "recommended_model": "persistence",
        }

    # Find best model by MAE
    best_model = min(maes, key=maes.get) if maes else "persistence"
    best_mae = maes[best_model]

    # Check if GPR adds value over persistence
    gpr_better = False
    if "gpr" in maes and "persistence" in maes:
        gpr_better = maes["gpr"] < maes["persistence"]

    # Only recommend GPR if it meaningfully outperforms persistence
    if best_model == "gpr" and gpr_better and best_mae < 0.1:
        recommended = "gpr"
    elif best_model == "linear_trend" and maes["linear_trend"] < maes.get("persistence", float("inf")):
        recommended = "linear_trend"
    else:
        recommended = "persistence"

    return {
        "display": True,
        "reason": f"{n_preds} predictions evaluated",
        "recommended_model": recommended,
        "best_mae": best_mae,
        "gpr_outperforms_persistence": gpr_better,
        "metrics_summary": {
            m: overall.get(m, {}).get("mae") for m in ["persistence", "linear_trend", "gpr"]
        },
    }