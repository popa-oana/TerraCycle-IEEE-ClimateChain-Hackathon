r"""
scripts/generate_ml_insights.py — Day 6C.3 corrected ML charts and AI insights

Generates four professional, scientifically honest trajectory charts and a
frontend-ready JSON export from the CORRECTED Day 6C.2B evaluation results.

Outputs
-------
- data/ml/plots/parcel_01_trajectory.png ... parcel_04_trajectory.png
- data/ml/ai_insights.json

This script is a VISUALIZATION / EXPORT task only. It does NOT retrain, tune or
change any model, and it never fits a model on test observations. All held-out
GPR predictions come from ``data/ml/evaluation_corrected/``. If that file is
missing required fields it is regenerated with the corrected evaluation
implementation (same kernel, same split, same persistence baseline).

The original Day 6C.2 outputs under ``data/ml/`` are never overwritten.

Run from the repository root:
    .\.venv\Scripts\python.exe scripts\generate_ml_insights.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless rendering

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.trajectory_evaluation import evaluate_all_parcels  # noqa: E402

DEFAULT_INPUT = REPO_ROOT / "data/features/observations_clean_4parcels.csv"
DEFAULT_EVAL_DIR = REPO_ROOT / "data/ml/evaluation_corrected"
DEFAULT_PLOT_DIR = REPO_ROOT / "data/ml/plots"
DEFAULT_JSON = REPO_ROOT / "data/ml/ai_insights.json"
DEFAULT_TRAIN_FRACTION = 0.75

CORRECTED_JSON = DEFAULT_EVAL_DIR / "trajectory_evaluation_corrected.json"
CORRECTED_CSV = DEFAULT_EVAL_DIR / "trajectory_test_predictions_corrected.csv"

REANALYSIS_NOTE = (
    "REANALYSIS of the previously inspected Day 6C.2 test set. Model kernel, "
    "hyperparameters, chronological split and persistence baseline are "
    "unchanged; only the time origin used for held-out predictions is fixed. "
    "This is not a fresh independent benchmark."
)

DISCLAIMER = (
    "These charts and metrics describe NDVI prediction only. They do not "
    "establish agronomic compliance, certification, or blockchain settlement "
    "eligibility."
)

SHARED_LIMITATIONS = [
    "Only four parcels and a single historical growing season (2024) were available.",
    "Held-out test sets are small (8-16 observations), so the error estimates are noisy.",
    "The shaded band is a nominal, uncalibrated GPR predictive interval; observed "
    "coverage on a handful of points does not prove calibration.",
    "Persistence outperformed the GP on every parcel, so the GP is not a reliable "
    "forecaster for this seasonal extrapolation.",
    "Predicting late-season NDVI from an early-season model is genuine extrapolation "
    "and is inherently difficult.",
    "Results describe NDVI prediction only and cannot authorize blockchain settlement.",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_observations(input_path: Path) -> pd.DataFrame:
    """Load genuine quality-approved Sentinel-2 NDVI observations."""
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
    return df


def _corrected_evaluation_is_complete(data: dict) -> bool:
    if "parcels" not in data or not isinstance(data["parcels"], list):
        return False
    for p in data["parcels"]:
        if not p.get("evaluated"):
            continue
        if not p.get("predictions"):
            return False
        for pred in p["predictions"]:
            for key in (
                "acquired_at", "actual_ndvi", "predicted_ndvi",
                "predicted_std", "baseline_prediction",
            ):
                if key not in pred:
                    return False
    return True


def load_corrected_evaluation(
    eval_dir: Path = DEFAULT_EVAL_DIR,
    input_path: Path = DEFAULT_INPUT,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
) -> dict:
    """
    Load the corrected evaluation, regenerating it (same model/split) if the
    file is missing or lacks the fields required for plotting.
    """
    eval_dir.mkdir(parents=True, exist_ok=True)
    corrected_json = eval_dir / "trajectory_evaluation_corrected.json"
    corrected_csv = eval_dir / "trajectory_test_predictions_corrected.csv"

    data: dict | None = None
    if corrected_json.exists():
        with open(corrected_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not _corrected_evaluation_is_complete(data):
            data = None

    if data is None:
        # Regenerate with the corrected implementation (no model/split change).
        data = evaluate_all_parcels(input_path, corrected_json, corrected_csv, train_fraction)
        with open(corrected_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["reanalysis_note"] = REANALYSIS_NOTE
        with open(corrected_json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return data


# ---------------------------------------------------------------------------
# AI insights JSON
# ---------------------------------------------------------------------------
def _explanation(parcel: dict) -> str:
    mae = parcel["gpr_mae"]
    base = parcel["baseline_mae"]
    winner = "persistence" if base < mae else "the Gaussian process"
    return (
        f"For {parcel['parcel_id']}, a Gaussian process was trained on the first "
        f"{parcel['n_train']} genuine Sentinel-2 NDVI observations and asked to "
        f"predict the later {parcel['n_test']} observations it had not seen. Its "
        f"mean absolute error was {mae:.3f}, while simply repeating the last "
        f"observed value (persistence) achieved {base:.3f}. On this parcel "
        f"{winner} performed better. The shaded band is the model's own nominal "
        f"95% predictive interval; it is a model-based estimate, not a guaranteed "
        f"95% coverage."
    )


def build_ai_insights(
    corrected: dict,
    observations: pd.DataFrame,
    generated_at: str | None = None,
) -> dict:
    """Build the frontend-ready insights document from corrected results."""
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    parcels_out = []
    for parcel in corrected.get("parcels", []):
        pid = parcel["parcel_id"]
        if not parcel.get("evaluated"):
            continue

        obs = observations[observations["parcel_id"] == pid].sort_values("_ts")
        n_train = int(parcel["n_train"])
        train_obs = obs.iloc[:n_train]
        test_obs = obs.iloc[n_train:]

        split_ts = pd.Timestamp(train_obs["_ts"].iloc[-1])
        split_date = split_ts.strftime("%Y-%m-%dT%H:%M:%SZ")

        gpr_predictions = [
            {
                "timestamp": str(p["acquired_at"]),
                "predicted_ndvi": float(p["predicted_ndvi"]),
                "predicted_std": float(p["predicted_std"]),
                "lower_95": float(p["lower_95"]),
                "upper_95": float(p["upper_95"]),
            }
            for p in parcel["predictions"]
        ]
        persistence_predictions = [
            {
                "timestamp": str(p["acquired_at"]),
                "predicted_ndvi": float(p["baseline_prediction"]),
            }
            for p in parcel["predictions"]
        ]

        parcels_out.append({
            "parcel_id": pid,
            "observations": [
                {
                    "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "ndvi": float(v),
                }
                for t, v in zip(obs["_ts"], obs["_ndvi"])
            ],
            "n_train": n_train,
            "n_test": int(parcel["n_test"]),
            "split_date": split_date,
            "test_period_start": str(parcel["test_period_start"]),
            "test_period_end": str(parcel["test_period_end"]),
            "gpr_predictions": gpr_predictions,
            "persistence_predictions": persistence_predictions,
            "metrics": {
                "gpr_mae": float(parcel["gpr_mae"]),
                "gpr_rmse": float(parcel["gpr_rmse"]),
                "baseline_mae": float(parcel["baseline_mae"]),
                "baseline_rmse": float(parcel["baseline_rmse"]),
                "observed_interval_coverage": float(
                    parcel["predictive_interval_coverage_95"]
                ),
                "gpr_better_than_persistence": bool(
                    parcel["gpr_better_than_baseline"]
                ),
            },
            "explanation": _explanation(parcel),
            "limitations": list(SHARED_LIMITATIONS),
        })

    return {
        "generated_at": generated_at,
        "title": (
            "TerraCycle Proof — corrected GPR NDVI trajectory insights (Day 6C.3)"
        ),
        "data_source": {
            "observations_file": str(DEFAULT_INPUT.relative_to(REPO_ROOT).as_posix()),
            "corrected_evaluation_file": str(
                CORRECTED_JSON.relative_to(REPO_ROOT).as_posix()
            ),
            "satellite": "Sentinel-2 L2A",
            "index": "NDVI = (B08 - B04) / (B08 + B04)",
        },
        "method": {
            "model": "Gaussian Process Regression, one model per parcel",
            "split": "chronological: first 75% of observations train, last 25% test",
            "baseline": "persistence (last training NDVI value)",
            "time_origin": (
                "single fixed origin = first training observation "
                "(corrected Day 6C.2B)"
            ),
            "reanalysis_note": REANALYSIS_NOTE,
        },
        "disclaimer": DISCLAIMER,
        "parcels": parcels_out,
    }


def write_ai_insights(insights: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
COLORS = {
    "real": "#9e9e9e",
    "train": "#1f77b4",
    "test": "#2ca02c",
    "gpr": "#d62728",
    "band": "#d62728",
    "baseline": "#ff7f0e",
    "split": "#222222",
}


def _style() -> None:
    plt.rcParams.update({
        "font.size": 11,
        "axes.titlesize": 15,
        "axes.labelsize": 12,
        "axes.titleweight": "bold",
        "legend.fontsize": 9.5,
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linewidth": 0.6,
    })


def generate_parcel_plot(
    parcel: dict,
    observations: pd.DataFrame,
    out_path: Path,
) -> None:
    """Render one parcel trajectory chart."""
    _style()
    pid = parcel["parcel_id"]
    obs = observations[observations["parcel_id"] == pid].sort_values("_ts")
    n_train = int(parcel["n_train"])
    train_obs = obs.iloc[:n_train]
    test_obs = obs.iloc[n_train:]

    fig, ax = plt.subplots(figsize=(11.5, 6.5))

    # 1. Real quality-approved observations (all), as markers only.
    ax.scatter(
        obs["_ts"], obs["_ndvi"], color=COLORS["real"], s=72, zorder=2,
        label="Real Sentinel-2 NDVI observations",
    )
    # 2. Training observations.
    ax.scatter(
        train_obs["_ts"], train_obs["_ndvi"], color=COLORS["train"], s=46,
        zorder=3, label="Training observations",
    )
    # 3. Chronologically held-out test observations.
    ax.scatter(
        test_obs["_ts"], test_obs["_ndvi"], color=COLORS["test"], s=54,
        zorder=4, label="Held-out test observations",
    )

    # 4. Train/test boundary.
    split_ts = pd.Timestamp(train_obs["_ts"].iloc[-1])
    ax.axvline(
        split_ts, color=COLORS["split"], linestyle="--", linewidth=1.6, zorder=1,
        label="Train/test split",
    )

    # 5/8. Corrected GPR predictions + nominal uncalibrated uncertainty band.
    preds = parcel["predictions"]
    pred_ts = [pd.Timestamp(p["acquired_at"]) for p in preds]
    pred_mean = np.array([p["predicted_ndvi"] for p in preds], dtype=float)
    pred_std = np.array([p["predicted_std"] for p in preds], dtype=float)
    lower = np.array([p["lower_95"] for p in preds], dtype=float)
    upper = np.array([p["upper_95"] for p in preds], dtype=float)

    ax.fill_between(
        pred_ts, lower, upper, color=COLORS["band"], alpha=0.18, zorder=1,
        label="Nominal GPR predictive interval (uncalibrated, not guaranteed 95%)",
    )
    ax.plot(
        pred_ts, pred_mean, color=COLORS["gpr"], marker="o", markersize=5,
        linewidth=2.0, zorder=5, label="Corrected GPR prediction (held-out)",
    )

    # 6. Persistence baseline.
    base_value = float(preds[0]["baseline_prediction"])
    ax.plot(
        pred_ts, [base_value] * len(pred_ts), color=COLORS["baseline"],
        linestyle="--", linewidth=1.8, zorder=4, label="Persistence baseline",
    )

    # 7. Metrics annotation.
    ax.text(
        0.015, 0.035,
        f"GPR held-out MAE: {parcel['gpr_mae']:.3f}   RMSE: {parcel['gpr_rmse']:.3f}\n"
        f"Persistence MAE: {parcel['baseline_mae']:.3f}   "
        f"RMSE: {parcel['baseline_rmse']:.3f}\n"
        f"{'GPR' if parcel['gpr_better_than_baseline'] else 'Persistence'} is better "
        f"on this parcel",
        transform=ax.transAxes, fontsize=10, va="bottom", ha="left",
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "white",
              "edgecolor": "#bbbbbb", "alpha": 0.95},
    )

    ax.set_title(f"{pid} — corrected GPR NDVI trajectory (Sentinel-2, 2024)")
    ax.set_xlabel("Acquisition date (UTC)")
    ax.set_ylabel("NDVI")
    ax.set_ylim(-0.15, 1.05)

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate()

    handles, labels = ax.get_legend_handles_labels()
    order = [3, 4, 0, 1, 2, 5, 6]  # keep split near top, band last
    ax.legend(
        [handles[i] for i in order], [labels[i] for i in order],
        loc="upper left", framealpha=0.95,
    )

    fig.text(
        0.5, 0.005,
        "Held-out GPR predictions use the corrected fixed time origin. "
        "Shaded band = nominal, uncalibrated GPR predictive interval. "
        "NDVI prediction only — not a compliance verdict.",
        ha="center", fontsize=8.5, color="#444444",
    )

    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_all_plots(
    corrected: dict, observations: pd.DataFrame, out_dir: Path
) -> list[Path]:
    paths = []
    for parcel in corrected.get("parcels", []):
        if not parcel.get("evaluated"):
            continue
        out_path = out_dir / f"{parcel['parcel_id']}_trajectory.png"
        generate_parcel_plot(parcel, observations, out_path)
        paths.append(out_path)
    return paths


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Day 6C.3 corrected ML charts and AI insights."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--eval-dir", default=str(DEFAULT_EVAL_DIR))
    parser.add_argument("--plot-dir", default=str(DEFAULT_PLOT_DIR))
    parser.add_argument("--output-json", default=str(DEFAULT_JSON))
    parser.add_argument("--train-fraction", type=float, default=DEFAULT_TRAIN_FRACTION)
    args = parser.parse_args()

    input_path = Path(args.input)
    eval_dir = Path(args.eval_dir)
    plot_dir = Path(args.plot_dir)
    output_json = Path(args.output_json)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    print("=" * 78)
    print("TERRACYCLE PROOF — CORRECTED ML VISUALIZATIONS (Day 6C.3)")
    print("=" * 78)
    print(f"Observations : {input_path}")
    print(f"Corrected eval: {eval_dir / 'trajectory_evaluation_corrected.json'}")
    print()

    observations = load_observations(input_path)
    corrected = load_corrected_evaluation(eval_dir, input_path, args.train_fraction)

    parcels = [p for p in corrected.get("parcels", []) if p.get("evaluated")]
    print(f"Parcels: {[p['parcel_id'] for p in parcels]}")

    # Charts
    plot_paths = generate_all_plots(corrected, observations, plot_dir)
    for p in plot_paths:
        print(f"  chart: {p}")

    # AI insights JSON
    insights = build_ai_insights(corrected, observations)
    write_ai_insights(insights, output_json)
    print(f"  JSON : {output_json}")

    print()
    print("NOTE: held-out GPR predictions come from the corrected Day 6C.2B")
    print("      evaluation. The original Day 6C.2 outputs were NOT modified.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
