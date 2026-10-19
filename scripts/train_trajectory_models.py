r"""
train_trajectory_models.py — Day 6C.1: Train per-parcel GPR trajectory models

Loads the existing four-parcel quality-approved dataset, trains a separate
Gaussian Process Regression model per parcel, generates predictions on a
historical date grid, and writes a JSON summary.

This is an experiment runner for model fitting sanity checks only.
It does NOT claim predictive accuracy or create compliance labels.

Run from the repository root:
    .\.venv\Scripts\python.exe scripts\train_trajectory_models.py

Optional:
    .\.venv\Scripts\python.exe scripts\train_trajectory_models.py `
        --input data/features/observations_clean_4parcels.csv `
        --output data/trajectory/summary.json `
        --grid-points 20
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.trajectory_model import (  # noqa: E402
    MIN_OBSERVATIONS,
    observations_to_training_data,
    predict_with_uncertainty,
    train_parcel_model,
)

DEFAULT_INPUT = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data/trajectory/summary.json"


def _build_date_grid(
    start_date: str,
    end_date: str,
    n_points: int,
) -> list[str]:
    """Generate an ISO date grid between start and end (inclusive)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    total_days = (end - start).days
    if total_days <= 0 or n_points <= 1:
        return [start_date]
    step = total_days / (n_points - 1)
    grid = []
    for i in range(n_points):
        day_offset = round(i * step)
        d = start + pd.Timedelta(days=day_offset)
        grid.append(d.strftime("%Y-%m-%d"))
    return grid


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train per-parcel GPR NDVI trajectory models (Day 6C.1)."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--grid-points", type=int, default=20)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    print("=" * 70)
    print("TERRACYCLE PROOF — GPR TRAJECTORY MODELS (Day 6C.1)")
    print("=" * 70)
    print(f"Input: {input_path}")
    print(f"Grid points: {args.grid_points}")
    print()

    # Load dataset
    try:
        df = pd.read_csv(input_path)
    except Exception as exc:
        print(f"ERROR: Failed to read CSV: {exc}")
        return 1

    required = {"parcel_id", "acquired_at", "ndvi_mean"}
    missing = required - set(df.columns)
    if missing:
        print(f"ERROR: Missing columns: {sorted(missing)}")
        return 1

    # Parse timestamps
    df["_ts"] = pd.to_datetime(df["acquired_at"], errors="coerce", utc=True)
    df = df[df["_ts"].notna()].copy()
    df["_ndvi"] = pd.to_numeric(df["ndvi_mean"], errors="coerce")
    df = df[df["_ndvi"].notna()].copy()
    df = df[(df["_ndvi"] >= -1) & (df["_ndvi"] <= 1)].copy()
    df = df.sort_values(["parcel_id", "_ts"]).reset_index(drop=True)

    if len(df) == 0:
        print("ERROR: No valid observations after filtering.")
        return 1

    # Train per-parcel models
    parcels = sorted(df["parcel_id"].unique())
    print(f"Parcels found: {parcels}")
    print(f"Total observations: {len(df)}")
    print()

    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_file": str(input_path),
        "grid_points": args.grid_points,
        "parcels": {},
    }

    for pid in parcels:
        parcel_df = df[df["parcel_id"] == pid].copy()
        n_obs = len(parcel_df)

        print(f"--- {pid} ({n_obs} observations) ---")

        # Convert timestamps to elapsed days
        timestamps_ns = parcel_df["_ts"].values.astype("datetime64[ns]").astype(np.int64)
        ndvi_values = parcel_df["_ndvi"].values.astype(float)
        elapsed_days, ndvi_values = observations_to_training_data(
            ndvi_values, timestamps_ns
        )

        # Train model
        result = train_parcel_model(pid, elapsed_days, ndvi_values)

        if not result["trained"]:
            print(f"  Training skipped: {result['error']}")
            summary["parcels"][pid] = {
                "observation_count": n_obs,
                "trained": False,
                "error": result["error"],
            }
            print()
            continue

        # Generate predictions on a date grid
        first_ts = parcel_df["_ts"].min()
        last_ts = parcel_df["_ts"].max()
        start_date = first_ts.strftime("%Y-%m-%d")
        end_date = last_ts.strftime("%Y-%m-%d")
        date_grid = _build_date_grid(start_date, end_date, args.grid_points)

        # Convert grid to elapsed days
        grid_datetimes = pd.to_datetime(date_grid, utc=True)
        grid_timestamps_ns = grid_datetimes.values.astype("datetime64[ns]").astype(np.int64)
        grid_elapsed, _ = observations_to_training_data(
            np.zeros(len(grid_timestamps_ns)), grid_timestamps_ns
        )

        pred = predict_with_uncertainty(result["model"], grid_elapsed)

        # Store summary (not full predictions to keep JSON small)
        pred_summary = []
        for i, date_str in enumerate(date_grid):
            pred_summary.append({
                "date": date_str,
                "elapsed_days": round(float(grid_elapsed[i]), 2),
                "ndvi_mean": round(float(pred["mean"][i]), 6),
                "ndvi_std": round(float(pred["std"][i]), 6),
            })

        print(f"  Trained: YES")
        print(f"  Elapsed days range: [{elapsed_days.min():.1f}, {elapsed_days.max():.1f}]")
        print(f"  NDVI range: [{ndvi_values.min():.4f}, {ndvi_values.max():.4f}]")
        print(f"  Prediction grid: {start_date} -> {end_date} ({args.grid_points} points)")
        print(f"  Sample prediction (mid-grid): "
              f"date={pred_summary[len(pred_summary)//2]['date']}, "
              f"ndvi={pred_summary[len(pred_summary)//2]['ndvi_mean']:.4f}, "
              f"std={pred_summary[len(pred_summary)//2]['ndvi_std']:.4f}")
        print()

        summary["parcels"][pid] = {
            "observation_count": n_obs,
            "trained": True,
            "error": None,
            "elapsed_days_range": [round(float(elapsed_days.min()), 2), round(float(elapsed_days.max()), 2)],
            "ndvi_range": [round(float(ndvi_values.min()), 6), round(float(ndvi_values.max()), 6)],
            "prediction_grid": pred_summary,
        }

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("=" * 70)
    print(f"Summary written: {output_path}")
    print("NOTE: This is an experimental regression module.")
    print("      No predictive accuracy is claimed from training-set predictions.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
