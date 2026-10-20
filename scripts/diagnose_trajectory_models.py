r"""
scripts/diagnose_trajectory_models.py — Day 6C.2A: Diagnose poor GPR performance

Runs a strictly diagnostic experiment:

  Step 1  Audit the existing implementation (time units, kernel, normalize_y,
          WhiteKernel/alpha, predictive std, test leakage, split validity,
          seasonal coincidence).
  Step 2  Time-ordered rolling-origin validation over ONLY the original
          training period for persistence, linear trend, the existing GPR
          configuration, and two pre-selected alternative GPR configurations.
  Step 3  Investigate why nominal 95% intervals are so narrow.

This script NEVER fits on, predicts on, or selects against the held-out test
observations. The original Day 6C.2 evaluation outputs are not modified; all
diagnostic artifacts are written under data/ml/diagnostics/.

Run from the repository root:
    .\.venv\Scripts\python.exe scripts\diagnose_trajectory_models.py

Optional:
    .\.venv\Scripts\python.exe scripts\diagnose_trajectory_models.py `
        --input data/features/observations_clean_4parcels.csv `
        --output-dir data/ml/diagnostics `
        --min-train-window 8 `
        --horizon 1
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning

# The WhiteKernel lower bound is intentionally permissive (1e-10), so the
# optimizer frequently reports that it hit that bound. This is a documented
# diagnostic finding (noise collapses toward zero), not a failure; the fitted
# values are captured in the manifest. Silence the repeated warnings so the
# runner output stays readable.
warnings.filterwarnings("ignore", category=ConvergenceWarning)

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.trajectory_diagnostics import (  # noqa: E402
    CANDIDATE_GPR_EXISTING,
    CANDIDATE_GPR_PERIODIC,
    CANDIDATE_GPR_SMOOTH,
    CANDIDATE_LINEAR,
    CANDIDATE_PERSISTENCE,
    DEFAULT_CANDIDATES,
    Z_95,
    aggregate_rolls,
    elapsed_days_from_origin,
    fitted_kernel_summary,
    original_train_test_split,
    rolling_origin_validation,
)
from backend.ml.trajectory_evaluation import persistence_baseline  # noqa: E402
from backend.ml.trajectory_model import (  # noqa: E402
    observations_to_training_data,
    train_parcel_model,
)

DEFAULT_INPUT = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/ml/diagnostics"


def _load_parcels(input_path: Path) -> dict[str, pd.DataFrame]:
    """Load and clean the four-parcel dataset, one DataFrame per parcel."""
    df = pd.read_csv(input_path)
    required = {"parcel_id", "acquired_at", "ndvi_mean"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    df["_ts"] = pd.to_datetime(df["acquired_at"], errors="coerce", utc=True)
    df = df[df["_ts"].notna()].copy()
    df["_ndvi"] = pd.to_numeric(df["ndvi_mean"], errors="coerce")
    df = df[df["_ndvi"].notna()].copy()
    df = df[(df["_ndvi"] >= -1) & (df["_ndvi"] <= 1)].copy()
    df = df.sort_values(["parcel_id", "_ts"]).reset_index(drop=True)

    return {
        pid: g.reset_index(drop=True)
        for pid, g in df.groupby("parcel_id", sort=True)
    }


def _audit_split(parcels: dict[str, pd.DataFrame], train_fraction: float) -> list[dict]:
    """Audit the original split and measure the feature-alignment mismatch."""
    findings: list[dict] = []

    for pid, parcel_df in parcels.items():
        train_df, test_df = original_train_test_split(parcel_df, train_fraction)

        train_ts_ns = train_df["_ts"].values.astype("datetime64[ns]").astype(np.int64)
        test_ts_ns = test_df["_ts"].values.astype("datetime64[ns]").astype(np.int64)

        # How the ORIGINAL evaluation computes test elapsed days:
        # observations_to_training_data re-zeroes on the test subset's minimum.
        buggy_test_elapsed, _ = observations_to_training_data(
            test_df["_ndvi"].values.astype(float), test_ts_ns
        )

        # The correct elapsed days use the TRAINING origin.
        correct_test_elapsed = elapsed_days_from_origin(test_ts_ns, int(train_ts_ns.min()))

        true_offset_days = float(correct_test_elapsed[0])

        # Do the buggy and correct coordinates ever coincide?
        train_elapsed, _ = observations_to_training_data(
            train_df["_ndvi"].values.astype(float), train_ts_ns
        )
        min_abs_gap = float(np.min(np.abs(buggy_test_elapsed[:, None] - train_elapsed[None, :])))

        findings.append({
            "parcel_id": pid,
            "n_total": int(len(parcel_df)),
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
            "train_elapsed_min": float(train_elapsed.min()),
            "train_elapsed_max": float(train_elapsed.max()),
            "buggy_test_elapsed_min": float(buggy_test_elapsed.min()),
            "buggy_test_elapsed_max": float(buggy_test_elapsed.max()),
            "correct_test_elapsed_min": float(correct_test_elapsed.min()),
            "correct_test_elapsed_max": float(correct_test_elapsed.max()),
            "test_true_offset_days": true_offset_days,
            "min_abs_coordinate_gap_to_train_days": min_abs_gap,
            "baseline_last_train_ndvi": float(train_df["_ndvi"].values[-1]),
        })

    return findings


def _audit_kernels(parcels: dict[str, pd.DataFrame], train_fraction: float) -> list[dict]:
    """Fit the existing GPR on the original training period and record hyperparams."""
    out: list[dict] = []

    for pid, parcel_df in parcels.items():
        train_df, _ = original_train_test_split(parcel_df, train_fraction)
        ts_ns = train_df["_ts"].values.astype("datetime64[ns]").astype(np.int64)
        elapsed, ndvi = observations_to_training_data(
            train_df["_ndvi"].values.astype(float), ts_ns
        )
        result = train_parcel_model(pid, elapsed, ndvi)
        if not result["trained"]:
            out.append({"parcel_id": pid, "trained": False, "error": result["error"]})
            continue

        summary = fitted_kernel_summary(result["model"])
        summary["parcel_id"] = pid
        summary["trained"] = True
        out.append(summary)

    return out


def _audit_uncertainty(parcels: dict[str, pd.DataFrame], train_fraction: float) -> list[dict]:
    """Analyse why nominal 95% intervals are narrow on the original test set.

    Uses ONLY the already-produced original predictions (data/ml/trajectory_
    evaluation.json) plus the audit geometry. No new test predictions are made.
    """
    eval_path = REPO_ROOT / "data/ml/trajectory_evaluation.json"
    out: list[dict] = []

    if not eval_path.exists():
        return out

    with open(eval_path, "r", encoding="utf-8") as f:
        original = json.load(f)

    for p in original.get("parcels", []):
        if not p.get("evaluated"):
            continue
        pid = p["parcel_id"]
        preds = p["predictions"]
        stds = np.array([x["predicted_std"] for x in preds], dtype=float)
        abs_err = np.array(
            [abs(x["actual_ndvi"] - x["predicted_ndvi"]) for x in preds], dtype=float
        )
        lower = np.array([x["lower_95"] for x in preds], dtype=float)
        upper = np.array([x["upper_95"] for x in preds], dtype=float)

        out.append({
            "parcel_id": pid,
            "n_test": len(preds),
            "mean_predicted_std": float(np.mean(stds)) if len(stds) else float("nan"),
            "median_predicted_std": float(np.median(stds)) if len(stds) else float("nan"),
            "min_predicted_std": float(np.min(stds)) if len(stds) else float("nan"),
            "max_predicted_std": float(np.max(stds)) if len(stds) else float("nan"),
            "mean_abs_error": float(np.mean(abs_err)) if len(abs_err) else float("nan"),
            "mean_interval_width": float(np.mean(upper - lower)) if len(stds) else float("nan"),
            "n_intervals_within_tolerance_1e-3": int(np.sum((upper - lower) < 1e-3)),
            "coverage_95": float(p["predictive_interval_coverage_95"]),
        })

    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Day 6C.2A diagnostics for GPR trajectory models."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--train-fraction", type=float, default=0.75)
    parser.add_argument("--min-train-window", type=int, default=8)
    parser.add_argument("--horizon", type=int, default=1)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    print("=" * 78)
    print("TERRACYCLE PROOF — GPR DIAGNOSTICS (Day 6C.2A)")
    print("=" * 78)
    print(f"Input:           {input_path}")
    print(f"Output directory: {output_dir}")
    print(f"Train fraction:  {args.train_fraction}")
    print()

    parcels = _load_parcels(input_path)
    print(f"Parcels: {list(parcels)}")
    print(f"Total observations: {sum(len(d) for d in parcels.values())}")
    print()

    # ------------------------------------------------------------------
    # Step 1a — split / feature-alignment audit
    # ------------------------------------------------------------------
    print("-" * 78)
    print("STEP 1 — AUDIT: split validity and feature alignment")
    print("-" * 78)
    split_audit = _audit_split(parcels, args.train_fraction)
    for f in split_audit:
        print(
            f"  {f['parcel_id']}: train_elapsed=[{f['train_elapsed_min']:.0f}, "
            f"{f['train_elapsed_max']:.0f}]d, "
            f"buggy_test_elapsed=[{f['buggy_test_elapsed_min']:.0f}, "
            f"{f['buggy_test_elapsed_max']:.0f}]d, "
            f"correct_test_offset={f['test_true_offset_days']:.0f}d, "
            f"min_coord_gap={f['min_abs_coordinate_gap_to_train_days']:.4f}d"
        )
    print()

    # ------------------------------------------------------------------
    # Step 1b — kernel hyperparameter audit
    # ------------------------------------------------------------------
    print("-" * 78)
    print("STEP 1 — AUDIT: fitted kernel hyperparameters (original training period)")
    print("-" * 78)
    kernel_audit = _audit_kernels(parcels, args.train_fraction)
    for k in kernel_audit:
        if not k.get("trained"):
            print(f"  {k['parcel_id']}: NOT TRAINED ({k.get('error')})")
            continue
        ls = next((v for key, v in k.items() if key.endswith("matern_length_scale")), None)
        noise = next((v for key, v in k.items() if key.endswith("white_noise_level")), None)
        print(
            f"  {k['parcel_id']}: matern_length_scale={ls} white_noise={noise} "
            f"y_mean={k.get('y_train_mean')} y_std={k.get('y_train_std')}"
        )
    print()

    # ------------------------------------------------------------------
    # Step 2 — rolling-origin validation on the original training period
    # ------------------------------------------------------------------
    print("-" * 78)
    print("STEP 2 — Rolling-origin validation (original training period ONLY)")
    print("-" * 78)
    all_rows: list[dict[str, object]] = []
    for pid, parcel_df in parcels.items():
        train_df, _ = original_train_test_split(parcel_df, args.train_fraction)
        rows = rolling_origin_validation(
            train_df,
            candidates=DEFAULT_CANDIDATES,
            min_train_window=args.min_train_window,
            horizon=args.horizon,
        )
        all_rows.extend(rows)
        n_folds = len({r["fold_train_size"] for r in rows})
        print(f"  {pid}: {n_folds} folds x {len(DEFAULT_CANDIDATES)} candidates")

    fold_df = pd.DataFrame(all_rows)
    fold_csv = output_dir / "validation_folds.csv"
    fold_df.to_csv(fold_csv, index=False)

    summary = aggregate_rolls(all_rows)
    summary_df = pd.DataFrame(summary)
    summary_csv = output_dir / "validation_summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    print()
    print("  Pooled validation metrics (original training period):")
    header = f"    {'candidate':<16} {'n':>5} {'MAE':>9} {'RMSE':>9} {'mean_std':>10} {'cov95':>8}"
    print(header)
    print("    " + "-" * (len(header) - 4))
    pooled = [s for s in summary if s["scope"] == "__all__"]
    order = {
        CANDIDATE_PERSISTENCE: 0,
        CANDIDATE_LINEAR: 1,
        CANDIDATE_GPR_EXISTING: 2,
        CANDIDATE_GPR_SMOOTH: 3,
        CANDIDATE_GPR_PERIODIC: 4,
    }
    for s in sorted(pooled, key=lambda x: order.get(x["candidate"], 99)):
        print(
            f"    {s['candidate']:<16} {s['n_folds']:>5} "
            f"{s['mae']:>9.4f} {s['rmse']:>9.4f} "
            f"{s['mean_predicted_std']:>10.4f} "
            f"{(s['coverage_95'] if not np.isnan(s['coverage_95']) else float('nan')):>8.2%}"
        )
    print()

    # ------------------------------------------------------------------
    # Step 3 — uncertainty audit
    # ------------------------------------------------------------------
    print("-" * 78)
    print("STEP 3 — AUDIT: nominal 95% interval narrowness (original test output)")
    print("-" * 78)
    uncertainty_audit = _audit_uncertainty(parcels, args.train_fraction)
    for u in uncertainty_audit:
        print(
            f"  {u['parcel_id']}: n={u['n_test']} mean_std={u['mean_predicted_std']:.5f} "
            f"min_std={u['min_predicted_std']:.5f} mean_abs_err={u['mean_abs_error']:.4f} "
            f"mean_width={u['mean_interval_width']:.5f} "
            f"tiny_intervals={u['n_intervals_within_tolerance_1e-3']} "
            f"coverage={u['coverage_95']:.2%}"
        )
    print()

    # ------------------------------------------------------------------
    # Write JSON artifacts
    # ------------------------------------------------------------------
    run_manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_file": str(input_path),
        "train_fraction": args.train_fraction,
        "min_train_window": args.min_train_window,
        "horizon": args.horizon,
        "candidates": list(DEFAULT_CANDIDATES),
        "z_95": Z_95,
        "test_data_used_for_selection": False,
        "split_audit": split_audit,
        "kernel_audit": kernel_audit,
        "validation_summary": summary,
        "uncertainty_audit": uncertainty_audit,
    }

    manifest_path = output_dir / "diagnostic_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(run_manifest, f, indent=2, ensure_ascii=False)

    print("=" * 78)
    print("Diagnostic artifacts written:")
    print(f"  {manifest_path}")
    print(f"  {fold_csv}")
    print(f"  {summary_csv}")
    print()
    print("NOTE: Original Day 6C.2 outputs were NOT modified.")
    print("      Test observations were NOT used for model selection.")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
