r"""
scripts/evaluate_trajectory_models_corrected.py — Day 6C.2B corrected evaluation

Re-runs the Day 6C.2 chronological evaluation for all four parcels after fixing
the time-origin defect in ``backend/ml/trajectory_evaluation.py``.

IMPORTANT: this is a REANALYSIS of the previously inspected test set, not a
fresh independent benchmark. It reuses the exact same model kernel,
hyperparameters, chronological split and persistence baseline as the original
run; the only change is that training and prediction now share a single,
consistent time origin.

The original outputs (``data/ml/trajectory_evaluation.json`` and
``data/ml/trajectory_test_predictions.csv``) are never overwritten. Corrected
results are written under ``data/ml/evaluation_corrected/``.

Run from the repository root:
    .\.venv\Scripts\python.exe scripts\evaluate_trajectory_models_corrected.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.trajectory_evaluation import evaluate_all_parcels  # noqa: E402

DEFAULT_INPUT = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
DEFAULT_ORIGINAL_JSON = REPO_ROOT / "data/ml/trajectory_evaluation.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/ml/evaluation_corrected"
DEFAULT_TRAIN_FRACTION = 0.75

REANALYSIS_NOTE = (
    "REANALYSIS of the previously inspected Day 6C.2 test set. Model kernel, "
    "hyperparameters, chronological split and persistence baseline are "
    "unchanged; only the time origin used for held-out predictions is fixed. "
    "This is not a fresh independent benchmark."
)


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_comparison(original: dict, corrected: dict) -> dict:
    """Build a per-parcel before/after comparison."""
    orig_by_id = {p["parcel_id"]: p for p in original.get("parcels", [])}
    corr_by_id = {p["parcel_id"]: p for p in corrected.get("parcels", [])}

    rows = []
    for pid in sorted(corr_by_id):
        c = corr_by_id[pid]
        o = orig_by_id.get(pid)
        if not c.get("evaluated") or not o or not o.get("evaluated"):
            rows.append({"parcel_id": pid, "evaluated": False})
            continue

        rows.append({
            "parcel_id": pid,
            "evaluated": True,
            "n_train": c["n_train"],
            "n_test": c["n_test"],
            "original_gpr_mae": o["gpr_mae"],
            "original_gpr_rmse": o["gpr_rmse"],
            "corrected_gpr_mae": c["gpr_mae"],
            "corrected_gpr_rmse": c["gpr_rmse"],
            "original_baseline_mae": o["baseline_mae"],
            "original_baseline_rmse": o["baseline_rmse"],
            "corrected_baseline_mae": c["baseline_mae"],
            "corrected_baseline_rmse": c["baseline_rmse"],
            "original_coverage_95": o["predictive_interval_coverage_95"],
            "corrected_coverage_95": c["predictive_interval_coverage_95"],
            "corrected_gpr_better_than_persistence": c["gpr_better_than_baseline"],
            "delta_gpr_mae": round(c["gpr_mae"] - o["gpr_mae"], 6),
            "delta_gpr_rmse": round(c["gpr_rmse"] - o["gpr_rmse"], 6),
        })

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reanalysis_note": REANALYSIS_NOTE,
        "input_file": corrected["input_file"],
        "train_fraction": corrected["train_fraction"],
        "parcels": rows,
    }


def _render_markdown(comparison: dict) -> str:
    lines = [
        "# Day 6C.2B — Corrected chronological evaluation (before/after)",
        "",
        "> **Reanalysis of the previously inspected test set, not a fresh",
        "> independent benchmark.** Kernel, hyperparameters, chronological split",
        "> and persistence baseline are unchanged; only the time origin used for",
        "> held-out predictions is fixed.",
        "",
        f"Generated: {comparison['generated_at']}",
        "",
        "| Parcel | N train | N test | GPR MAE (orig) | GPR MAE (corr) | "
        "GPR RMSE (orig) | GPR RMSE (corr) | Baseline MAE (corr) | "
        "Coverage 95% (orig) | Coverage 95% (corr) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in comparison["parcels"]:
        if not r.get("evaluated"):
            lines.append(f"| {r['parcel_id']} | SKIP | - | - | - | - | - | - | - | - |")
            continue
        lines.append(
            f"| {r['parcel_id']} | {r['n_train']} | {r['n_test']} | "
            f"{r['original_gpr_mae']:.4f} | {r['corrected_gpr_mae']:.4f} | "
            f"{r['original_gpr_rmse']:.4f} | {r['corrected_gpr_rmse']:.4f} | "
            f"{r['corrected_baseline_mae']:.4f} | "
            f"{r['original_coverage_95']:.2%} | "
            f"{r['corrected_coverage_95']:.2%} |"
        )
    lines += [
        "",
        "GPR better than persistence on the corrected run: "
        + ", ".join(
            f"{r['parcel_id']}={'YES' if r.get('corrected_gpr_better_than_persistence') else 'NO'}"
            for r in comparison["parcels"] if r.get("evaluated")
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Day 6C.2B corrected chronological evaluation."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--original-json", default=str(DEFAULT_ORIGINAL_JSON))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--train-fraction", type=float, default=DEFAULT_TRAIN_FRACTION)
    args = parser.parse_args()

    input_path = Path(args.input)
    original_json = Path(args.original_json)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    corrected_json = output_dir / "trajectory_evaluation_corrected.json"
    corrected_csv = output_dir / "trajectory_test_predictions_corrected.csv"
    comparison_json = output_dir / "comparison.json"
    comparison_md = output_dir / "COMPARISON.md"

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1
    if not original_json.exists():
        print(f"ERROR: Original evaluation not found: {original_json}")
        return 1

    print("=" * 78)
    print("TERRACYCLE PROOF — CORRECTED GPR EVALUATION (Day 6C.2B)")
    print("=" * 78)
    print("NOTE: reanalysis of the previously inspected test set; not a fresh")
    print("      independent benchmark. Kernel/hyperparameters/split unchanged.")
    print()

    # 1. Corrected evaluation (fixed time origin).
    corrected = evaluate_all_parcels(
        input_path, corrected_json, corrected_csv, args.train_fraction
    )

    # 2. Label the corrected JSON as a reanalysis.
    with open(corrected_json, "r", encoding="utf-8") as f:
        corrected_labeled = json.load(f)
    corrected_labeled["reanalysis_note"] = REANALYSIS_NOTE
    with open(corrected_json, "w", encoding="utf-8") as f:
        json.dump(corrected_labeled, f, indent=2, ensure_ascii=False)

    # 3. Comparison against the original run.
    original = _load_json(original_json)
    comparison = _build_comparison(original, corrected)
    with open(comparison_json, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    with open(comparison_md, "w", encoding="utf-8") as f:
        f.write(_render_markdown(comparison))

    # 4. Console table.
    print(
        f"{'Parcel':<12} {'Ntr':>4} {'Nte':>4} {'MAE_old':>8} {'MAE_new':>8} "
        f"{'RMSE_old':>9} {'RMSE_new':>9} {'Base_new':>9} "
        f"{'Cov_old':>8} {'Cov_new':>8} {'GPR>Base':>9}"
    )
    print("-" * 95)
    for r in comparison["parcels"]:
        if not r.get("evaluated"):
            print(f"{r['parcel_id']:<12} {'SKIP':>4} {'-':>4}")
            continue
        print(
            f"{r['parcel_id']:<12} {r['n_train']:>4} {r['n_test']:>4} "
            f"{r['original_gpr_mae']:>8.4f} {r['corrected_gpr_mae']:>8.4f} "
            f"{r['original_gpr_rmse']:>9.4f} {r['corrected_gpr_rmse']:>9.4f} "
            f"{r['corrected_baseline_mae']:>9.4f} "
            f"{r['original_coverage_95']:>7.2%} {r['corrected_coverage_95']:>7.2%} "
            f"{'YES' if r['corrected_gpr_better_than_persistence'] else 'NO':>9}"
        )

    print()
    print("Corrected artifacts written under:")
    print(f"  {corrected_json}")
    print(f"  {corrected_csv}")
    print(f"  {comparison_json}")
    print(f"  {comparison_md}")
    print()
    print("Original outputs were NOT modified:")
    print(f"  {original_json}")
    print(f"  {REPO_ROOT / 'data/ml/trajectory_test_predictions.csv'}")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
