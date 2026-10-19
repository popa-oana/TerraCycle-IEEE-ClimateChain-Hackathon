r"""
prepare_ml_dataset.py — Day 5A: build the ML-ready observation dataset

Reads the real NDVI / pixel-quality exports from `data/ndvi/`, standardises
them to the agreed schema, applies the existing quality rules and writes:

    data/features/observations_clean.csv
    data/features/observations_quality_report.json

Dataset schema (one row = one parcel acquisition):

    parcel_id, acquired_at, scene_id, ndvi_mean, valid_pixel_fraction

Processing rules
----------------
1. One source file per parcel. `_quality` exports are preferred over
   NDVI-only exports because only the former carry real quality metadata;
   full season is preferred over the June-only test window. Alternate files
   for the same parcel are reported as skipped, never merged (merging the
   June subset into the full season would duplicate timestamps).
2. Timestamps are parsed as UTC and written as `YYYY-MM-DDTHH:MM:SSZ`.
3. Rows with a missing/unparseable timestamp or a missing/out-of-range NDVI
   are excluded (structural exclusions). A missing NDVI is never imputed.
4. Duplicate `(parcel_id, acquired_at)` rows are removed deterministically,
   keeping the first occurrence in the source file.
5. Pixel quality is evaluated with the existing
   `backend.ml.quality.filter_observations_by_quality()` function (Rule C,
   default threshold 0.50 from `backend/ml/processing_config.json`).
   Missing quality metadata is treated as insufficient, never as valid.
6. Accepted observations are sorted chronologically (ties by parcel_id).

Raw exports are opened read-only and are never modified. No observation is
interpolated or invented. When nothing passes the filters, a header-only CSV
and an honest report explaining the blocker are still written.

Run from the repository root:
    .\.venv\Scripts\python.exe scripts\prepare_ml_dataset.py

Optional:
    .\.venv\Scripts\python.exe scripts\prepare_ml_dataset.py `
        --input-dir data/ndvi `
        --output data/features/observations_clean.csv `
        --report data/features/observations_quality_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

# Windows console may use cp1252; force UTF-8 so diacritics do not fail.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Anchor imports to the repository root.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.quality import filter_observations_by_quality  # noqa: E402

DATASET_COLUMNS: list[str] = [
    "parcel_id",
    "acquired_at",
    "scene_id",
    "ndvi_mean",
    "valid_pixel_fraction",
]

# Lower index = higher preference. The June exports are subsets of the full
# season, so they are never merged with the full-season export.
SOURCE_PRIORITY: tuple[str, ...] = (
    "_2024_quality.csv",
    "_june_2024_quality.csv",
    "_2024.csv",
    "_june_2024.csv",
    "_clean.csv",
)
# Filename matching must try the longest suffix first: `parcel_01_june_2024.csv`
# also ends with `_2024.csv`.
SOURCE_SUFFIXES_BY_LENGTH: tuple[str, ...] = tuple(
    sorted(SOURCE_PRIORITY, key=len, reverse=True)
)

DEFAULT_INPUT_DIR = REPO_ROOT / "data/ndvi"
DEFAULT_OUTPUT_CSV = REPO_ROOT / "data/features/observations_clean.csv"
DEFAULT_REPORT_JSON = REPO_ROOT / "data/features/observations_quality_report.json"
DEFAULT_CONFIG = REPO_ROOT / "backend/ml/processing_config.json"

DEFAULT_MIN_VALID_PIXEL_FRACTION = 0.50


# ============================================================
# Source discovery
# ============================================================

def _match_source_name(filename: str) -> Optional[tuple[str, str]]:
    """
    Split an export filename into `(parcel_id, suffix)`.

    Returns None when the filename does not match a known export suffix.
    """
    for suffix in SOURCE_SUFFIXES_BY_LENGTH:
        if filename.endswith(suffix) and len(filename) > len(suffix):
            return filename[: -len(suffix)], suffix
    return None


def discover_sources(input_dir: Path | str) -> tuple[dict[str, Path], list[dict[str, str]], list[dict[str, str]]]:
    """
    Find one preferred source export per parcel in `input_dir`.

    Returns
    -------
    sources : dict[parcel_id, Path]
        Chosen source file per parcel (highest-priority suffix available).
    skipped : list of dict
        Alternate files for parcels that already have a preferred source.
    ignored : list of dict
        CSV files that do not match any known export suffix.
    """
    directory = Path(input_dir)
    if not directory.exists():
        return {}, [], []

    by_parcel: dict[str, list[tuple[int, Path]]] = {}
    ignored: list[dict[str, str]] = []

    for path in sorted(directory.glob("*.csv")):
        match = _match_source_name(path.name)
        if match is None:
            ignored.append(
                {
                    "file": _display_path(path),
                    "reason": "unrecognized CSV filename (no known NDVI/quality export suffix)",
                }
            )
            continue
        parcel_id, suffix = match
        by_parcel.setdefault(parcel_id, []).append(
            (SOURCE_PRIORITY.index(suffix), path)
        )

    sources: dict[str, Path] = {}
    skipped: list[dict[str, str]] = []
    for parcel_id in sorted(by_parcel):
        options = sorted(by_parcel[parcel_id], key=lambda item: (item[0], str(item[1])))
        chosen = options[0][1]
        sources[parcel_id] = chosen
        for _, alternate in options[1:]:
            skipped.append(
                {
                    "parcel_id": parcel_id,
                    "file": _display_path(alternate),
                    "reason": (
                        "alternate source for the same parcel; not merged "
                        f"(preferred: {chosen.name})"
                    ),
                }
            )

    return sources, skipped, ignored


def _display_path(path: Path) -> str:
    """Prefer a repository-relative POSIX path for stable reports."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return str(path)


# ============================================================
# Loading / normalisation
# ============================================================

def _load_source(path: Path, parcel_id: str) -> pd.DataFrame:
    """
    Read one export and normalise column names without modifying the file.

    Required: a timestamp column (`acquired_at` or `date`) and an NDVI column
    (`ndvi_mean` or `band_unnamed`). Missing required columns raise a
    ValueError instead of silently producing an empty dataset.
    """
    df = pd.read_csv(path, dtype=str)

    if "date" in df.columns and "acquired_at" not in df.columns:
        df = df.rename(columns={"date": "acquired_at"})
    if "band_unnamed" in df.columns and "ndvi_mean" not in df.columns:
        df = df.rename(columns={"band_unnamed": "ndvi_mean"})

    if "acquired_at" not in df.columns:
        raise ValueError(
            f"{path.name}: missing timestamp column 'acquired_at' (or 'date')"
        )
    if "ndvi_mean" not in df.columns:
        raise ValueError(
            f"{path.name}: missing NDVI column 'ndvi_mean' (or 'band_unnamed')"
        )

    if "parcel_id" in df.columns:
        present = df["parcel_id"].dropna().astype(str).str.strip()
        unexpected = sorted(set(present) - {parcel_id} - {""})
        if unexpected:
            raise ValueError(
                f"{path.name}: contains parcel_id values {unexpected}, "
                f"expected only '{parcel_id}'"
            )

    df["parcel_id"] = parcel_id
    if "scene_id" not in df.columns:
        df["scene_id"] = pd.NA
    if "valid_pixel_fraction" not in df.columns:
        df["valid_pixel_fraction"] = pd.NA

    df["source_file"] = path.name
    return df


def _resolve_threshold(
    config_path: Path | str | None,
    explicit: Optional[float],
) -> float:
    """Use the explicit threshold, else the processing config, else 0.50."""
    if explicit is not None:
        threshold = float(explicit)
    elif config_path is not None and Path(config_path).exists():
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        threshold = float(
            config.get("min_valid_pixel_fraction", DEFAULT_MIN_VALID_PIXEL_FRACTION)
        )
    else:
        threshold = DEFAULT_MIN_VALID_PIXEL_FRACTION

    if not 0.0 <= threshold <= 1.0:
        raise ValueError(
            f"min_valid_pixel_fraction must be in [0, 1], got {threshold}"
        )
    return threshold


def _iso_range(timestamps: pd.Series) -> dict[str, Optional[str]]:
    """Return the UTC ISO date range of a timestamp series."""
    if len(timestamps) == 0:
        return {"start": None, "end": None}
    return {
        "start": timestamps.min().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": timestamps.max().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ============================================================
# Main preparation pipeline
# ============================================================

def prepare_ml_dataset(
    input_dir: Path | str,
    output_csv: Path | str,
    report_json: Path | str,
    config_path: Path | str | None = None,
    min_valid_pixel_fraction: Optional[float] = None,
) -> dict[str, Any]:
    """
    Build `observations_clean.csv` and its quality report.

    Returns the report dictionary (also written to `report_json`).
    Raises ValueError only for structurally invalid source files or an
    invalid quality threshold; an empty result is reported, not fabricated.
    """
    input_path = Path(input_dir)
    output_path = Path(output_csv)
    report_path = Path(report_json)
    threshold = _resolve_threshold(config_path, min_valid_pixel_fraction)

    sources, skipped_sources, ignored_files = discover_sources(input_path)

    # --- Load the single preferred source per parcel ---
    frames = [
        _load_source(path, parcel_id)
        for parcel_id, path in sorted(sources.items())
    ]
    if frames:
        raw = pd.concat(frames, ignore_index=True)
    else:
        raw = pd.DataFrame(columns=[*DATASET_COLUMNS, "source_file"])

    original_count = int(len(raw))

    # --- Parse fields explicitly; no implicit coercion or imputation ---
    if original_count:
        timestamps = pd.to_datetime(
            raw["acquired_at"], format="ISO8601", errors="coerce", utc=True
        )
        ndvi = pd.to_numeric(raw["ndvi_mean"], errors="coerce")
        fractions = pd.to_numeric(raw["valid_pixel_fraction"], errors="coerce")
    else:
        timestamps = pd.Series([], dtype="datetime64[ns, UTC]")
        ndvi = pd.Series([], dtype=float)
        fractions = pd.Series([], dtype=float)

    work = raw.copy()
    work["_acquired_at"] = timestamps
    work["_ndvi"] = ndvi
    work["_vpf"] = fractions

    source_date_range = _iso_range(work["_acquired_at"].dropna())

    # --- Structural exclusions (timestamp first, then NDVI) ---
    missing_timestamp_count = int(work["_acquired_at"].isna().sum())
    work = work[work["_acquired_at"].notna()].copy()

    invalid_ndvi_mask = (
        work["_ndvi"].isna()
        | (work["_ndvi"] < -1)
        | (work["_ndvi"] > 1)
    )
    invalid_ndvi_count = int(invalid_ndvi_mask.sum())
    work = work[~invalid_ndvi_mask].copy()

    # --- Duplicate handling: one observation per (parcel, timestamp) ---
    work = work.sort_values(
        by=["_acquired_at", "parcel_id"], kind="mergesort"
    ).reset_index(drop=True)
    rows_before_dedup = int(len(work))
    work = work.drop_duplicates(
        subset=["parcel_id", "_acquired_at"], keep="first"
    ).reset_index(drop=True)
    duplicate_count = rows_before_dedup - int(len(work))

    missing_quality_count = int(work["_vpf"].isna().sum())

    # --- Rule C: reuse the existing quality filtering function ---
    work["valid_pixel_fraction"] = work["_vpf"]
    quality = filter_observations_by_quality(
        work, min_valid_pixel_fraction=threshold
    )
    accepted = quality["df_valid"].copy()
    rejected = quality["df_invalid"].copy()

    quality_reasons = (
        {
            str(reason): int(count)
            for reason, count in rejected["quality_reason"]
            .fillna("unknown")
            .value_counts()
            .sort_index()
            .items()
        }
        if len(rejected) > 0
        else {}
    )

    missing_quality_excluded = sum(
        count
        for reason, count in quality_reasons.items()
        if reason == "Missing valid_pixel_fraction"
    )
    invalid_fraction_excluded = sum(
        count
        for reason, count in quality_reasons.items()
        if reason.startswith("Invalid valid_pixel_fraction")
    )
    below_threshold_excluded = sum(
        count
        for reason, count in quality_reasons.items()
        if reason.startswith("valid_pixel_fraction=") and " < " in reason
    )

    # --- Standardised, chronologically sorted output ---
    accepted = accepted.sort_values(
        by=["_acquired_at", "parcel_id"], kind="mergesort"
    )
    dataset = pd.DataFrame(
        {
            "parcel_id": accepted["parcel_id"].astype(str),
            "acquired_at": accepted["_acquired_at"].dt.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "scene_id": accepted["scene_id"],
            "ndvi_mean": accepted["_ndvi"].astype(float).round(6),
            "valid_pixel_fraction": accepted["_vpf"].astype(float).round(4),
        },
        columns=DATASET_COLUMNS,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(
        output_path,
        index=False,
        columns=DATASET_COLUMNS,
        na_rep="",
        lineterminator="\n",
    )
    dataset_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()

    accepted_count = int(len(dataset))
    excluded_count = original_count - accepted_count
    unique_parcel_count = int(dataset["parcel_id"].nunique())
    unique_timestamp_count = int(dataset["acquired_at"].nunique())

    # --- Per-parcel accounting over all structurally loaded rows ---
    observations_per_parcel: dict[str, dict[str, Any]] = {}
    for parcel_id in sorted(sources):
        source_rows = int((raw["parcel_id"] == parcel_id).sum())
        accepted_rows = int((dataset["parcel_id"] == parcel_id).sum())
        observations_per_parcel[parcel_id] = {
            "source_file": _display_path(sources[parcel_id]),
            "original_observations": source_rows,
            "accepted_observations": accepted_rows,
            "excluded_observations": source_rows - accepted_rows,
        }

    # --- Honest suitability assessment / blocker ---
    if not sources:
        blocker: Optional[str] = (
            f"No recognized NDVI/quality CSV exports found in {_display_path(input_path)}"
        )
    elif original_count == 0:
        blocker = "The selected source exports contain no observations."
    elif accepted_count == 0:
        blocker = (
            "No observation passed structural and pixel-quality filtering "
            f"(min_valid_pixel_fraction={threshold:.2f})."
        )
    else:
        blocker = None

    warnings: list[str] = []
    if sources and len(sources) == 1:
        warnings.append(
            "Only one parcel is available; multiple timestamps from one parcel "
            "are not independent parcels/samples."
        )
    if blocker is None and unique_timestamp_count == accepted_count:
        warnings.append(
            "All accepted observations are from distinct timestamps; revisit "
            "counts are not available."
        )
    if any(
        not observations_per_parcel[p]["accepted_observations"]
        for p in observations_per_parcel
    ):
        warnings.append(
            "At least one source parcel contributed zero accepted observations."
        )

    report: dict[str, Any] = {
        "schema_version": "ml-observations-v1",
        "dataset_csv": _display_path(output_path),
        "dataset_sha256": dataset_sha256,
        "dataset_columns": DATASET_COLUMNS,
        "dataset_logical_types": {
            "parcel_id": "string",
            "acquired_at": "string (UTC ISO-8601, YYYY-MM-DDTHH:MM:SSZ)",
            "scene_id": "string or null (never fabricated)",
            "ndvi_mean": "float in [-1, 1]",
            "valid_pixel_fraction": "float in [0, 1]",
        },
        "input_directory": _display_path(input_path),
        "min_valid_pixel_fraction": threshold,
        "source_parcel_count": len(sources),
        "unique_parcel_count": unique_parcel_count,
        "original_observation_count": original_count,
        "accepted_observation_count": accepted_count,
        "excluded_observation_count": excluded_count,
        "excluded_by_stage": {
            "missing_or_unparseable_timestamp": missing_timestamp_count,
            "missing_or_out_of_range_ndvi": invalid_ndvi_count,
            "duplicate_parcel_timestamp": duplicate_count,
            "pixel_quality": int(len(rejected)),
        },
        "quality_exclusion_reasons": quality_reasons,
        "quality_exclusion_categories": {
            "missing_quality_metadata": missing_quality_excluded,
            "below_min_valid_pixel_fraction": below_threshold_excluded,
            "invalid_valid_pixel_fraction": invalid_fraction_excluded,
        },
        "missing_quality_information_count": missing_quality_count,
        "source_date_range": source_date_range,
        "accepted_date_range": _iso_range(
            accepted["_acquired_at"].dropna()
        ),
        "unique_timestamp_count": unique_timestamp_count,
        "source_files_used": {
            parcel_id: _display_path(path)
            for parcel_id, path in sorted(sources.items())
        },
        "source_files_skipped": skipped_sources,
        "ignored_files": ignored_files,
        "observations_per_parcel": observations_per_parcel,
        "suitable_for_feature_engineering": accepted_count > 0,
        "blocker": blocker,
        "warnings": warnings,
        "notes": [
            "Observations are parcel-level aggregates from Sentinel-2 L2A "
            "(B04/B08 NDVI, SCL classes 4-5 as valid).",
            "Raw Copernicus/openEO exports are read-only inputs and are never "
            "modified by this script.",
            "No interpolation, imputation or synthetic observation is added.",
            "The provisional parcel polygon is manual digitisation and may "
            "contain more than one agricultural field; the dataset cannot "
            "separate fields inside it.",
            "No labels are included; this dataset is not sufficient to train "
            "a supervised model on its own.",
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")

    return report


# ============================================================
# CLI
# ============================================================

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the ML-ready observation dataset from real NDVI/quality "
            "exports (Day 5A). Raw files are never modified."
        )
    )
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--report", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--min-valid-pixel-fraction",
        type=float,
        default=None,
        help=(
            "Override the Rule C threshold; defaults to "
            "min_valid_pixel_fraction from --config (0.50)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        report = prepare_ml_dataset(
            input_dir=args.input_dir,
            output_csv=args.output,
            report_json=args.report,
            config_path=args.config,
            min_valid_pixel_fraction=args.min_valid_pixel_fraction,
        )
    except ValueError as exc:
        print(f"EROARE: {exc}")
        return 1

    print(f"Dataset scris: {report['dataset_csv']}")
    print(f"Raport calitate: {_display_path(Path(args.report))}")
    print(f"Observații originale: {report['original_observation_count']}")
    print(f"Observații acceptate: {report['accepted_observation_count']}")
    print(f"Observații excluse: {report['excluded_observation_count']}")
    print(f"Parcele unice: {report['unique_parcel_count']}")
    date_range = report["accepted_date_range"]
    print(f"Interval acceptat: {date_range['start']} -> {date_range['end']}")
    print(f"SHA-256 dataset: {report['dataset_sha256']}")
    if report["source_files_skipped"]:
        print(
            f"Surse alternative ignorate: {len(report['source_files_skipped'])} "
            "(nu au fost combinate)"
        )
    if report["blocker"]:
        print(f"BLOCANT: {report['blocker']}")
    for warning in report["warnings"]:
        print(f"ATENȚIE: {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
