"""
backend/ml/features.py — Parcel-level satellite feature engineering

Day 5B for TerraCycle Proof. Converts quality-approved Sentinel-2
observations (one row = one parcel acquisition) into one descriptive feature
record per parcel, inside a commitment window.

This module only builds features. It does NOT:
- create labels or pseudo-labels,
- consume rule verdicts (`conform`/`nonconform`/`inconclusive`) as inputs,
- train a model or compute accuracy,
- interpolate missing dates or invent measurements.

Input schema (from `data/features/observations_clean.csv`):
    parcel_id, acquired_at, scene_id, ndvi_mean, valid_pixel_fraction

Only `parcel_id`, `acquired_at` and `ndvi_mean` are required.
`date` / `band_unnamed` aliases are accepted for reuse with raw exports.

Commitment-window convention (same as `backend.ml.rules.verify_parcel` and
`backend.ml.quality.compute_temporal_coverage`): timestamps are UTC and the
window is **inclusive start, exclusive end**:

    window_start <= acquired_at < window_end

Features (documented units):
    ndvi_mean                  dimensionless NDVI mean over accepted observations
    ndvi_min                   dimensionless NDVI minimum
    ndvi_max                   dimensionless NDVI maximum
    ndvi_std                   population standard deviation (ddof=0), dimensionless
    ndvi_range                 ndvi_max - ndvi_min, dimensionless
    ndvi_trend                 ordinary-least-squares slope of NDVI per elapsed
                               day (NDVI units / day), using actual acquisition
                               dates. Null when fewer than two distinct
                               observation dates exist.
    observation_count          number of accepted observations (integer)
    observation_span_days      days between first and last accepted acquisition
    mean_valid_pixel_fraction  mean genuine valid-pixel fraction in [0, 1]
    min_valid_pixel_fraction   minimum genuine valid-pixel fraction in [0, 1]

Missing quality metadata is never assumed valid: when
`valid_pixel_fraction` is present, Rule C is re-applied defensively with
`backend.ml.quality.filter_observations_by_quality`; when the whole column is
absent the NDVI features are still computed but the quality features are null
and the diagnostics flag `quality_metadata_available = False`.

Reproducibility: identical input + identical window produce identical
features. Output ordering is deterministic (sorted by `parcel_id`).

Multi-period limitation: features are grouped by `parcel_id` only. With more
than one commitment period, the grouping key must become
`(parcel_id, window_start, window_end)`; otherwise observations from different
periods would be merged. This module accepts a single window and documents the
limitation instead of combining periods silently.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from backend.ml.quality import filter_observations_by_quality

FEATURES_VERSION = "satellite-features-v1.0.0"

FEATURE_NAMES: tuple[str, ...] = (
    "ndvi_mean",
    "ndvi_min",
    "ndvi_max",
    "ndvi_std",
    "ndvi_range",
    "ndvi_trend",
    "observation_count",
    "observation_span_days",
    "mean_valid_pixel_fraction",
    "min_valid_pixel_fraction",
)

FEATURE_UNITS: dict[str, str] = {
    "ndvi_mean": "NDVI units (dimensionless, [-1, 1])",
    "ndvi_min": "NDVI units (dimensionless, [-1, 1])",
    "ndvi_max": "NDVI units (dimensionless, [-1, 1])",
    "ndvi_std": "NDVI units (population standard deviation, ddof=0)",
    "ndvi_range": "NDVI units (ndvi_max - ndvi_min)",
    "ndvi_trend": "NDVI units per elapsed day (OLS slope vs actual dates)",
    "observation_count": "count of accepted observations",
    "observation_span_days": "days between first and last accepted acquisition",
    "mean_valid_pixel_fraction": "fraction in [0, 1]",
    "min_valid_pixel_fraction": "fraction in [0, 1]",
}

STD_CONVENTION = "population standard deviation (ddof=0)"
TREND_DEFINITION = (
    "ordinary-least-squares slope of ndvi versus elapsed days since the first "
    "distinct acquisition date; null when fewer than two distinct dates exist"
)

DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "parcel_id",
    "observation_count",
    "distinct_observation_dates",
    "first_observation",
    "last_observation",
    "observation_span_days",
    "quality_metadata_available",
    "quality_excluded_count",
    "trend_defined",
    "meets_min_observations",
    "evidence_sufficiency",
    "notes",
)

_ROUND_DECIMALS = 6


def _empty_features() -> pd.DataFrame:
    return pd.DataFrame(columns=["parcel_id", *FEATURE_NAMES])


def _empty_diagnostics() -> pd.DataFrame:
    return pd.DataFrame(columns=list(DIAGNOSTIC_COLUMNS))


def _parse_window(
    window_start: Any,
    window_end: Any,
) -> tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    """
    Parse an optional commitment window into UTC timestamps.

    Both bounds must be supplied together. Inclusive start / exclusive end is
    enforced by the caller. An explicitly supplied but invalid window raises
    ValueError instead of silently using the whole dataset.
    """
    if window_start is None and window_end is None:
        return None, None

    if window_start is None or window_end is None:
        raise ValueError(
            "Invalid commitment window: both window_start and window_end are "
            "required"
        )

    try:
        start = pd.to_datetime(window_start, errors="raise", utc=True)
        end = pd.to_datetime(window_end, errors="raise", utc=True)
    except Exception as exc:  # noqa: BLE001 - re-raised as a clear message
        raise ValueError(
            "Invalid commitment window: could not parse "
            f"window_start={window_start!r}, window_end={window_end!r} as UTC "
            "dates"
        ) from exc

    if pd.isna(start) or pd.isna(end):
        raise ValueError(
            "Invalid commitment window: could not parse "
            f"window_start={window_start!r}, window_end={window_end!r} as UTC "
            "dates"
        )
    if end <= start:
        raise ValueError(
            "Invalid commitment window: window_end "
            f"({end.isoformat()}) must be strictly after window_start "
            f"({start.isoformat()})"
        )
    return start, end


def _linear_trend(dates: pd.DatetimeIndex, values: np.ndarray) -> Optional[float]:
    """
    OLS slope of `values` against elapsed days since the first date.

    Returns None when fewer than two distinct dates or zero time variance are
    available, so an undefined slope is never fabricated. No interpolation is
    performed; only the acquisition dates that actually exist are used.
    """
    if len(dates) < 2:
        return None
    elapsed = np.asarray(
        (dates - dates.min()).total_seconds(), dtype=float
    ) / 86400.0
    y = np.asarray(values, dtype=float)
    x_mean = float(elapsed.mean())
    y_mean = float(y.mean())
    sxx = float(((elapsed - x_mean) ** 2).sum())
    if sxx <= 0.0:
        return None
    sxy = float(((elapsed - x_mean) * (y - y_mean)).sum())
    return sxy / sxx


def _iso(timestamp: Any) -> Optional[str]:
    if timestamp is None or pd.isna(timestamp):
        return None
    return pd.Timestamp(timestamp).strftime("%Y-%m-%dT%H:%M:%SZ")


def _features_for_parcel(
    group: pd.DataFrame,
    min_observations: int,
    quality_excluded: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute the feature record and diagnostic record for one parcel."""
    parcel_id = str(group["parcel_id"].iloc[0])
    ndvi = group["_ndvi"].astype(float)
    fractions = group["_fraction"]

    quality_available = bool(parcel_id and fractions.notna().any())

    observation_count = int(len(group))
    first_ts = group["_ts"].min()
    last_ts = group["_ts"].max()
    span_days = float((last_ts - first_ts).total_seconds() / 86400.0)

    # Trend uses distinct acquisition dates; duplicate dates are averaged so the
    # regression stays well-defined without inventing dates.
    per_date = group.groupby(group["_ts"].dt.normalize())["_ndvi"].mean()
    distinct_dates = len(per_date)
    trend = _linear_trend(pd.DatetimeIndex(per_date.index), per_date.to_numpy(dtype=float))

    if quality_available:
        mean_fraction: Optional[float] = float(fractions.mean())
        min_fraction: Optional[float] = float(fractions.min())
    else:
        mean_fraction = None
        min_fraction = None

    feature_row: dict[str, Any] = {
        "parcel_id": parcel_id,
        "ndvi_mean": round(float(ndvi.mean()), _ROUND_DECIMALS),
        "ndvi_min": round(float(ndvi.min()), _ROUND_DECIMALS),
        "ndvi_max": round(float(ndvi.max()), _ROUND_DECIMALS),
        "ndvi_std": round(float(ndvi.std(ddof=0)), _ROUND_DECIMALS),
        "ndvi_range": round(float(ndvi.max() - ndvi.min()), _ROUND_DECIMALS),
        "ndvi_trend": (
            None if trend is None else round(float(trend), _ROUND_DECIMALS)
        ),
        "observation_count": observation_count,
        "observation_span_days": round(span_days, _ROUND_DECIMALS),
        "mean_valid_pixel_fraction": (
            None if mean_fraction is None else round(mean_fraction, _ROUND_DECIMALS)
        ),
        "min_valid_pixel_fraction": (
            None if min_fraction is None else round(min_fraction, _ROUND_DECIMALS)
        ),
    }

    notes: list[str] = []
    if not quality_available:
        notes.append(
            "quality metadata unavailable: valid_pixel_fraction is null; "
            "quality features are null"
        )
    if trend is None:
        notes.append(
            "trend undefined: fewer than two distinct observation dates"
        )
    meets_min = observation_count >= min_observations
    if not meets_min:
        notes.append(
            f"fewer than min_observations={min_observations} quality-approved "
            "observations: descriptive features only, does not qualify for "
            "compliance verification"
        )
    if quality_excluded:
        notes.append(
            f"{quality_excluded} observation(s) excluded by the pixel-quality "
            "rule before feature aggregation"
        )

    diagnostic_row: dict[str, Any] = {
        "parcel_id": parcel_id,
        "observation_count": observation_count,
        "distinct_observation_dates": int(distinct_dates),
        "first_observation": _iso(first_ts),
        "last_observation": _iso(last_ts),
        "observation_span_days": round(span_days, _ROUND_DECIMALS),
        "quality_metadata_available": quality_available,
        "quality_excluded_count": quality_excluded,
        "trend_defined": trend is not None,
        "meets_min_observations": meets_min,
        "evidence_sufficiency": "sufficient" if meets_min else "insufficient",
        "notes": notes,
    }
    return feature_row, diagnostic_row


def build_features(
    observations: Optional[pd.DataFrame],
    window_start: Any = None,
    window_end: Any = None,
    min_valid_pixel_fraction: float = 0.50,
    min_observations: int = 5,
) -> dict[str, Any]:
    """
    Build one feature record per parcel from quality-approved observations.

    Parameters
    ----------
    observations : DataFrame
        Observations with at least `parcel_id`, `acquired_at` (or `date`) and
        `ndvi_mean` (or `band_unnamed`). `valid_pixel_fraction` is optional.
    window_start, window_end : str | datetime | None
        Commitment window (UTC, inclusive start / exclusive end). Both must be
        given together; an invalid window raises ValueError. When both are
        None, all observations are used.
    min_valid_pixel_fraction : float
        Rule C threshold, re-applied defensively when the quality column is
        present (reused from `backend.ml.quality`).
    min_observations : int
        Threshold used only to label evidence sufficiency in the diagnostics;
        it does NOT change the verifier's thresholds.

    Returns
    -------
    dict with:
        features : DataFrame  (one row per parcel, sorted by parcel_id)
        diagnostics : DataFrame  (one row per parcel)
        plus metadata (feature_names, features_version, window, counts, ...).
    """
    if min_valid_pixel_fraction < 0 or min_valid_pixel_fraction > 1:
        raise ValueError(
            "min_valid_pixel_fraction must be in [0, 1], got "
            f"{min_valid_pixel_fraction}"
        )
    if min_observations < 1:
        raise ValueError("min_observations must be >= 1")

    start, end = _parse_window(window_start, window_end)

    metadata: dict[str, Any] = {
        "features_version": FEATURES_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "std_convention": STD_CONVENTION,
        "trend_definition": TREND_DEFINITION,
        "window_start": _iso(start) if start is not None else None,
        "window_end": _iso(end) if end is not None else None,
        "min_observations": int(min_observations),
        "min_valid_pixel_fraction": float(min_valid_pixel_fraction),
        "quality_metadata_available": False,
        "counts": {
            "input_observation_count": 0,
            "invalid_timestamp_excluded": 0,
            "invalid_ndvi_excluded": 0,
            "missing_parcel_id_excluded": 0,
            "out_of_window_excluded": 0,
            "quality_excluded": 0,
            "used_observation_count": 0,
        },
    }

    if observations is None or len(observations) == 0:
        return {
            "features": _empty_features(),
            "diagnostics": _empty_diagnostics(),
            **metadata,
        }

    df = observations.copy()
    if "date" in df.columns and "acquired_at" not in df.columns:
        df = df.rename(columns={"date": "acquired_at"})
    if "band_unnamed" in df.columns and "ndvi_mean" not in df.columns:
        df = df.rename(columns={"band_unnamed": "ndvi_mean"})

    required = {"parcel_id", "acquired_at", "ndvi_mean"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Observation input missing required columns: {sorted(missing)}"
        )

    metadata["counts"]["input_observation_count"] = int(len(df))

    df["_ts"] = pd.to_datetime(
        df["acquired_at"], format="ISO8601", errors="coerce", utc=True
    )
    df["_ndvi"] = pd.to_numeric(df["ndvi_mean"], errors="coerce")
    has_quality_column = "valid_pixel_fraction" in df.columns
    if has_quality_column:
        df["_fraction"] = pd.to_numeric(df["valid_pixel_fraction"], errors="coerce")
    else:
        df["_fraction"] = np.nan

    # --- Structural exclusions (no imputation) ---
    invalid_ts = int(df["_ts"].isna().sum())
    df = df[df["_ts"].notna()].copy()

    invalid_ndvi_mask = (
        df["_ndvi"].isna() | (df["_ndvi"] < -1) | (df["_ndvi"] > 1)
    )
    invalid_ndvi = int(invalid_ndvi_mask.sum())
    df = df[~invalid_ndvi_mask].copy()

    parcel_present = df["parcel_id"].notna() & (
        df["parcel_id"].astype(str).str.strip() != ""
    )
    missing_parcel = int((~parcel_present).sum())
    df = df[parcel_present].copy()

    metadata["counts"]["invalid_timestamp_excluded"] = invalid_ts
    metadata["counts"]["invalid_ndvi_excluded"] = invalid_ndvi
    metadata["counts"]["missing_parcel_id_excluded"] = missing_parcel

    # --- Commitment-window filter (inclusive start / exclusive end, UTC) ---
    if start is not None and end is not None:
        before_window = int(len(df))
        df = df[(df["_ts"] >= start) & (df["_ts"] < end)].copy()
        metadata["counts"]["out_of_window_excluded"] = before_window - int(len(df))

    # --- Defensive Rule C (only when the quality column is present) ---
    quality_excluded = 0
    quality_excluded_by_parcel: dict[str, int] = {}
    if has_quality_column:
        metadata["quality_metadata_available"] = bool(df["_fraction"].notna().any())
        quality = filter_observations_by_quality(
            df, min_valid_pixel_fraction=min_valid_pixel_fraction
        )
        quality_excluded = int(quality["invalid_count"])
        if quality_excluded:
            quality_excluded_by_parcel = {
                str(parcel): int(count)
                for parcel, count in quality["df_invalid"]
                .groupby("parcel_id")
                .size()
                .items()
            }
        df = quality["df_valid"].copy()
    else:
        metadata["quality_metadata_available"] = False

    metadata["counts"]["quality_excluded"] = quality_excluded

    if len(df) == 0:
        return {
            "features": _empty_features(),
            "diagnostics": _empty_diagnostics(),
            **metadata,
        }

    metadata["counts"]["used_observation_count"] = int(len(df))

    feature_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    for parcel_id, group in df.sort_values("_ts", kind="mergesort").groupby(
        "parcel_id", sort=True
    ):
        feature_row, diagnostic_row = _features_for_parcel(
            group,
            min_observations,
            quality_excluded_by_parcel.get(str(parcel_id), 0),
        )
        feature_rows.append(feature_row)
        diagnostic_rows.append(diagnostic_row)

    features = pd.DataFrame(feature_rows, columns=["parcel_id", *FEATURE_NAMES])
    features = features.sort_values("parcel_id").reset_index(drop=True)
    diagnostics = pd.DataFrame(diagnostic_rows, columns=list(DIAGNOSTIC_COLUMNS))
    diagnostics = diagnostics.sort_values("parcel_id").reset_index(drop=True)

    return {
        "features": features,
        "diagnostics": diagnostics,
        **metadata,
    }
