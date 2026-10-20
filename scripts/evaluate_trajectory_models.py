r"""
evaluate_trajectory_models.py — Day 6C.2: Chronological evaluation runner

Evaluates per-parcel GPR models on held-out test observations using a strict
chronological train/test split. Prints a concise comparison table.

This is an experiment runner for honest evaluation only.
It does NOT claim predictive accuracy or create compliance labels.

Run from the repository root:
    .\.venv\Scripts\python.exe scripts\evaluate_trajectory_models.py

Optional:
    .\.venv\Scripts\python.exe scripts\evaluate_trajectory_models.py `
        --input data/features/observations_clean_4parcels.csv `
        --output-json data/ml/trajectory_evaluation.json `
        --output-csv data/ml/trajectory_test_predictions.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.trajectory_evaluation import evaluate_all_parcels  # noqa: E402

DEFAULT_INPUT = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "data/ml/trajectory_evaluation.json"
DEFAULT_OUTPUT_CSV = REPO_ROOT / "data/ml/trajectory_test_predictions.csv"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate per-parcel GPR models on held-out test data (Day 6C.2)."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--train-fraction", type=float, default=0.75)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_json = Path(args.output_json)
    output_csv = Path(args.output_csv)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    print("=" * 70)
    print("TERRACYCLE PROOF — GPR EVALUATION (Day 6C.2)")
    print("=" * 70)
    print(f"Input: {input_path}")
    print(f"Train fraction: {args.train_fraction}")
    print()

    try:
        summary = evaluate_all_parcels(
            input_path, output_json, output_csv, args.train_fraction
        )
    except Exception as exc:
        print(f"ERROR: Evaluation failed: {exc}")
        return 1

    # Print comparison table
    print(f"{'Parcel':<12} {'N_train':>8} {'N_test':>7} {'GPR_MAE':>9} {'GPR_RMSE':>9} "
          f"{'Base_MAE':>9} {'Base_RMSE':>9} {'GPR>Base':>9} {'Coverage':>9}")
    print("-" * 90)

    for p in summary["parcels"]:
        if p["evaluated"]:
            print(f"{p['parcel_id']:<12} {p['n_train']:>8} {p['n_test']:>7} "
                  f"{p['gpr_mae']:>9.4f} {p['gpr_rmse']:>9.4f} "
                  f"{p['baseline_mae']:>9.4f} {p['baseline_rmse']:>9.4f} "
                  f"{'YES' if p['gpr_better_than_baseline'] else 'NO':>9} "
                  f"{p['predictive_interval_coverage_95']:>9.2%}")
        else:
            print(f"{p['parcel_id']:<12} {'SKIP':>8} {'-':>7} {'-':>9} {'-':>9} "
                  f"{'-':>9} {'-':>9} {'-':>9} {'-':>9}")
            print(f"  Reason: {p['reason']}")

    print()
    print(f"JSON output: {output_json}")
    print(f"CSV output:  {output_csv}")
    print()
    print("NOTE: Nominal 95% intervals are not guaranteed to provide calibrated 95% coverage.")
    print("      Predictive std is a model-based estimate, not a validated uncertainty.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
