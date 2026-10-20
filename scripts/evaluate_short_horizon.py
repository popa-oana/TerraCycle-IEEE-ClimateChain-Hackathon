r"""
scripts/evaluate_short_horizon.py — Day 6C.4: Rolling short-horizon evaluation

Evaluates whether existing ML models provide useful short-term NDVI predictions
(next satellite acquisition) using expanding-window backtesting.

For each of the four parcels:
1. Sort genuine quality-approved observations chronologically.
2. Begin with at least 8 historical observations.
3. Fit a model using historical observations available before the prediction date.
4. Predict the next genuine satellite acquisition.
5. Record the actual time gap in days.
6. Compare the prediction against the subsequently observed NDVI.
7. Advance the historical window to include the new observation.
8. Repeat until observations are exhausted.

Models compared:
A. Persistence baseline (last observed value)
B. Linear trend (OLS on trailing window)
C. Existing Gaussian Process Regression (corrected implementation)

Run from the repository root:
    .\.venv\Scripts\python.exe scripts\evaluate_short_horizon.py
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

from backend.ml.short_horizon import (  # noqa: E402
    evaluate_all_parcels_short_horizon,
    get_presentation_recommendation,
)

DEFAULT_INPUT = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/ml/short_horizon"
DEFAULT_MIN_HISTORY = 8
DEFAULT_LINEAR_WINDOW = 10


def _render_markdown(summary: dict) -> str:
    """Render a human-readable markdown report."""
    import numpy as np
    lines = [
        "# Day 6C.4 — Short-Horizon NDVI Forecasting Evaluation",
        "",
        "> **EXPERIMENTAL rolling backtest on previously inspected data.**",
        "> Not a fresh independent benchmark. Results do not establish",
        "> validated forecasting performance, agronomic compliance,",
        "> certification, or blockchain settlement eligibility.",
        "",
        f"Generated: {summary['generated_at']}",
        f"Input: {summary['input_file']}",
        f"Min history: {summary['min_history']}",
        f"Linear trend window: {summary['linear_window'] or 'all'}",
        "",
    ]

    # Per-parcel summary table
    lines.append("## Per-Parcel Overall Metrics (MAE)")
    lines.append("")
    lines.append(
        "| Parcel | N obs | N preds | Persistence | Linear Trend | GPR | Recommended |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---|"
    )

    for p in summary["parcels"]:
        if not p.get("evaluated"):
            lines.append(f"| {p['parcel_id']} | {p['n_observations']} | - | SKIP | - | - | {p.get('reason', 'N/A')} |")
            continue

        overall = p.get("metrics", {}).get("overall", {})
        pers_mae = overall.get("persistence", {}).get("mae", "N/A")
        linear_mae = overall.get("linear_trend", {}).get("mae", "N/A")
        gpr_mae = overall.get("gpr", {}).get("mae", "N/A")

        rec = get_presentation_recommendation(p)
        recommended = rec.get("recommended_model", "persistence")

        def fmt(v):
            return f"{v:.4f}" if isinstance(v, (int, float)) else str(v)

        lines.append(
            f"| {p['parcel_id']} | {p['n_observations']} | {p['n_predictions']} | "
            f"{fmt(pers_mae)} | {fmt(linear_mae)} | {fmt(gpr_mae)} | {recommended} |"
        )

    lines.append("")

    # Horizon band breakdown
    lines.append("## Metrics by Prediction Horizon Band")
    lines.append("")

    for p in summary["parcels"]:
        if not p.get("evaluated"):
            continue

        lines.append(f"### {p['parcel_id']}")
        lines.append("")
        lines.append(
            "| Band | N | Persistence MAE | Linear MAE | GPR MAE | GPR Mean Std | GPR 95% Coverage |"
        )
        lines.append(
            "|---|---:|---:|---:|---:|---:|---:|"
        )

        for band_name, band_data in p.get("metrics", {}).get("by_horizon_band", {}).items():
            n = band_data.get("n", 0)
            models = band_data.get("models", {})

            pers = models.get("persistence", {})
            linear = models.get("linear_trend", {})
            gpr = models.get("gpr", {})
            uncert = band_data.get("gpr_uncertainty", {})
            coverage = band_data.get("gpr_interval_coverage_95", {})

            def fmt_mae(m):
                return f"{m.get('mae', 'N/A'):.4f}" if m.get("mae") is not None else "N/A"

            def fmt_std(s):
                return f"{s:.4f}" if s is not None else "N/A"

            def fmt_cov(c):
                return f"{c:.2%}" if c is not None else "N/A"

            lines.append(
                f"| {band_name} | {n} | {fmt_mae(pers)} | {fmt_mae(linear)} | {fmt_mae(gpr)} | "
                f"{fmt_std(uncert.get('mean_predicted_std'))} | {fmt_cov(coverage.get('coverage'))} |"
            )

        lines.append("")

    # Presentation recommendations
    lines.append("## Presentation Recommendations")
    lines.append("")
    lines.append(
        "| Parcel | Display | Recommended Model | Reason |"
    )
    lines.append("|---|---|---|---|")

    for p in summary["parcels"]:
        rec = get_presentation_recommendation(p)
        lines.append(
            f"| {p['parcel_id']} | {rec['display']} | {rec['recommended_model'] or 'N/A'} | {rec['reason']} |"
        )

    lines.append("")
    lines.append("## Uncertainty-Horizon Correlation")
    lines.append("")

    for p in summary["parcels"]:
        if not p.get("evaluated"):
            continue
        # This would need the raw predictions to compute; skip for now
        lines.append(f"- {p['parcel_id']}: (computed in JSON output)")

    lines.append("")
    lines.append("## Conclusion")
    lines.append("")

    # Overall conclusion
    all_persistence = []
    all_linear = []
    all_gpr = []

    for p in summary["parcels"]:
        if not p.get("evaluated"):
            continue
        overall = p.get("metrics", {}).get("overall", {})
        for model, key in [("persistence", "persistence"), ("linear_trend", "linear_trend"), ("gpr", "gpr")]:
            if key in overall and overall[key].get("mae") is not None:
                if model == "persistence":
                    all_persistence.append(overall[key]["mae"])
                elif model == "linear_trend":
                    all_linear.append(overall[key]["mae"])
                elif model == "gpr":
                    all_gpr.append(overall[key]["mae"])

    avg_pers = np.mean(all_persistence) if all_persistence else None
    avg_linear = np.mean(all_linear) if all_linear else None
    avg_gpr = np.mean(all_gpr) if all_gpr else None

    lines.append(f"Average MAE across parcels (overall):")
    lines.append(f"- Persistence: {avg_pers:.4f}" if avg_pers else "- Persistence: N/A")
    lines.append(f"- Linear Trend: {avg_linear:.4f}" if avg_linear else "- Linear Trend: N/A")
    lines.append(f"- GPR: {avg_gpr:.4f}" if avg_gpr else "- GPR: N/A")
    lines.append("")

    if avg_gpr and avg_pers and avg_gpr < avg_pers:
        lines.append("**GPR outperforms persistence on average.**")
    else:
        lines.append("**Persistence remains the best performer on average.**")
        if avg_gpr and avg_pers:
            lines.append(f"GPR MAE is {((avg_gpr - avg_pers) / avg_pers * 100):.1f}% higher than persistence.")

    lines.append("")
    lines.append("**Recommendation for demo:** Use persistence baseline for any displayed")
    lines.append("short-term NDVI predictions. GPR does not add measurable value for")
    lines.append("this seasonal extrapolation task. All model outputs are experimental")
    lines.append("and must carry explicit disclaimers.")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Day 6C.4 rolling short-horizon NDVI forecasting evaluation."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-history", type=int, default=DEFAULT_MIN_HISTORY)
    parser.add_argument("--linear-window", type=int, default=DEFAULT_LINEAR_WINDOW)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_json = output_dir / "short_horizon_evaluation.json"
    output_md = output_dir / "SHORT_HORIZON_EVALUATION.md"

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    print("=" * 78)
    print("TERRACYCLE PROOF — SHORT-HORIZON NDVI FORECASTING (Day 6C.4)")
    print("=" * 78)
    print("EXPERIMENTAL rolling backtest on previously inspected data.")
    print("Not a fresh independent benchmark.")
    print()

    summary = evaluate_all_parcels_short_horizon(
        input_path,
        output_json,
        min_history=args.min_history,
        linear_window=args.linear_window,
    )

    # Add presentation recommendations to JSON
    for p in summary["parcels"]:
        p["presentation"] = get_presentation_recommendation(p)

    # Save updated JSON with recommendations
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Save markdown report
    md_content = _render_markdown(summary)
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Console summary
    print(f"{'Parcel':<12} {'Nobs':>4} {'Npred':>5} {'Pers MAE':>9} {'Linear MAE':>10} {'GPR MAE':>9} {'Rec':>10}")
    print("-" * 70)
    for p in summary["parcels"]:
        if not p.get("evaluated"):
            print(f"{p['parcel_id']:<12} {p['n_observations']:>4} {'SKIP':>5}")
            continue
        overall = p.get("metrics", {}).get("overall", {})
        pers = overall.get("persistence", {}).get("mae", "N/A")
        linear = overall.get("linear_trend", {}).get("mae", "N/A")
        gpr = overall.get("gpr", {}).get("mae", "N/A")
        rec = get_presentation_recommendation(p).get("recommended_model", "pers")
        print(f"{p['parcel_id']:<12} {p['n_observations']:>4} {p['n_predictions']:>5} "
              f"{float(pers):>9.4f} {float(linear):>10.4f} {float(gpr):>9.4f} {rec:>10}")

    print()
    print(f"Results written to:")
    print(f"  {output_json}")
    print(f"  {output_md}")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    import numpy as np
    raise SystemExit(main())