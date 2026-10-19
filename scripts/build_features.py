r"""
build_features.py — Day 5B: parcel-level satellite features

Reads the Day 5A quality-controlled observations and writes one descriptive
feature record per parcel inside the configured commitment window:

    input : data/features/observations_clean.csv
    output: data/features/parcel_features.csv
            data/features/parcel_features_report.json

The commitment window comes from `backend/ml/processing_config.json`
(`time_interval.start` / `time_interval.end`, inclusive start / exclusive end,
UTC). All quality parameters are reused from the same config; nothing is
hard-coded twice and no verifier threshold is changed.

This script does NOT create labels, does NOT train a model and does NOT
interpolate missing measurements. The raw input CSV is opened read-only.

Run from the repository root:
    .\.venv\Scripts\python.exe scripts\build_features.py

Optional overrides:
    ... --window-start 2024-04-01 --window-end 2024-07-01
    ... --min-valid-pixel-fraction 0.5 --min-observations 5
    ... --input data/features/observations_clean.csv `
        --output data/features/parcel_features.csv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.features import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_UNITS,
    FEATURES_VERSION,
    STD_CONVENTION,
    TREND_DEFINITION,
    build_features,
)

DEFAULT_CONFIG = REPO_ROOT / "backend/ml/processing_config.json"
DEFAULT_INPUT = REPO_ROOT / "data/features/observations_clean.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data/features/parcel_features.csv"
DEFAULT_REPORT = REPO_ROOT / "data/features/parcel_features_report.json"


def _display_path(path: Path) -> str:
    """Prefer a repository-relative POSIX path for stable reports."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return str(path)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build parcel-level satellite features (Day 5B). No labels, no "
            "model training, no interpolation."
        )
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--window-start", default=None)
    parser.add_argument("--window-end", default=None)
    parser.add_argument("--min-valid-pixel-fraction", type=float, default=None)
    parser.add_argument("--min-observations", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    config = _load_json(Path(args.config))
    time_interval = config.get("time_interval", {}) if config else {}
    window_start = args.window_start or time_interval.get("start")
    window_end = args.window_end or time_interval.get("end")
    min_valid_pixel_fraction = (
        args.min_valid_pixel_fraction
        if args.min_valid_pixel_fraction is not None
        else config.get("min_valid_pixel_fraction", 0.50) if config else 0.50
    )
    min_observations = (
        args.min_observations
        if args.min_observations is not None
        else config.get("min_valid_observations", 5) if config else 5
    )

    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report)

    if not input_path.exists() or input_path.stat().st_size == 0:
        print(
            "EROARE: lipsește intrarea "
            f"{_display_path(input_path)}. Rulați mai întâi "
            "scripts/prepare_ml_dataset.py (Day 5A)."
        )
        return 1

    input_bytes = input_path.read_bytes()
    input_sha256 = hashlib.sha256(input_bytes).hexdigest()

    try:
        observations = pd.read_csv(
            input_path, dtype={"parcel_id": str, "scene_id": str}
        )
        result = build_features(
            observations,
            window_start=window_start,
            window_end=window_end,
            min_valid_pixel_fraction=min_valid_pixel_fraction,
            min_observations=min_observations,
        )
    except ValueError as exc:
        print(f"EROARE: {exc}")
        return 1

    features = result["features"]
    diagnostics = result["diagnostics"]
    counts = result["counts"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output_path, index=False, na_rep="", lineterminator="\n")
    output_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()

    warnings: list[str] = []
    if len(features) == 0:
        warnings.append(
            "No parcel produced features (no observations passed the window "
            "and quality filters)."
        )
    if len(features) == 1:
        warnings.append(
            "Only one parcel is available: supervised generalization cannot "
            "be evaluated and rows from the same parcel are not independent "
            "samples."
        )
    if not result["quality_metadata_available"]:
        warnings.append(
            "valid_pixel_fraction was not available: quality features are "
            "null and the evidence quality is unknown."
        )
    insufficient = (
        diagnostics.loc[~diagnostics["meets_min_observations"], "parcel_id"].tolist()
        if len(diagnostics)
        else []
    )
    if insufficient:
        warnings.append(
            "Parcels with fewer than "
            f"{result['min_observations']} quality-approved observations "
            f"(descriptive features only): {insufficient}."
        )

    report = {
        "schema_version": "parcel-features-v1",
        "features_version": result["features_version"],
        "input_csv": _display_path(input_path),
        "input_sha256": input_sha256,
        "output_csv": _display_path(output_path),
        "output_sha256": output_sha256,
        "feature_names": result["feature_names"],
        "feature_units": FEATURE_UNITS,
        "std_convention": result["std_convention"],
        "trend_definition": result["trend_definition"],
        "commitment_window": {
            "start": result["window_start"],
            "end": result["window_end"],
            "convention": "inclusive start, exclusive end, UTC",
            "source": (
                "backend/ml/processing_config.json time_interval"
                if result["window_start"] and result["window_end"]
                else "none (all observations used)"
            ),
        },
        "min_valid_pixel_fraction": result["min_valid_pixel_fraction"],
        "min_observations": result["min_observations"],
        "quality_metadata_available": result["quality_metadata_available"],
        "parcel_count": int(len(features)),
        "used_observation_count": counts["used_observation_count"],
        "observation_counts": counts,
        "parcels": diagnostics.to_dict(orient="records"),
        "warnings": warnings,
        "notes": [
            "Features are descriptive statistics of real Sentinel-2 "
            "observations; they are not labels and no verdict is used as an "
            "input feature.",
            "Missing measurements are excluded, never imputed; no synthetic "
            "parcel is created.",
            "The commitment window is inclusive at the start and exclusive at "
            "the end, in UTC.",
            "Grouping limitation: features are grouped by parcel_id only. With "
            "multiple commitment periods the grouping key must become "
            "(parcel_id, window_start, window_end) so periods are never "
            "combined silently.",
            "The raw input CSV is opened read-only and is not modified.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            report, f, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False
        )
        f.write("\n")

    if input_path.read_bytes() != input_bytes:
        print("EROARE: fișierul de intrare a fost modificat (nu ar trebui).")
        return 1

    print(f"Features scrise: {report['output_csv']}")
    print(f"Raport: {_display_path(report_path)}")
    print(f"Parcele: {report['parcel_count']}")
    print(f"Observații folosite: {report['used_observation_count']}")
    window = report["commitment_window"]
    print(f"Fereastră: {window['start']} -> {window['end']}")
    print(f"SHA-256 features: {output_sha256}")
    if features.empty:
        print("BLOCANT: nicio parcelă nu a produs features.")
    for warning in warnings:
        print(f"ATENȚIE: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
