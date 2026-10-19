"""
backend/ml/quality.py — Data quality, filtering and temporal coverage utilities

Day 4 implementation for TerraCycle Proof satellite data quality assessment.

This module provides:
- Pixel validity fraction assessment (Rule C: >= 0.50 required)
- Temporal coverage calculation (Rule B: >= 0.50 required, 10-day intervals)
- Observation quality filtering
- Reusable quality evaluation functions
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

# --- Sentinel-2 SCL policy (Day 4) ---
# Only these Scene Classification Layer classes are treated as usable for
# agricultural NDVI: 4 = vegetation, 5 = not vegetated (bare soil visible).
# All other classes (clouds, shadows, water, defective, unclassified, snow)
# are excluded.
ACCEPTED_SCL_CLASSES: tuple[int, ...] = (4, 5)

# --- SCL eligibility policy (pixel-coverage denominator) ---
# SCL classes 1..11 carry an actual scene classification. Class 0 is the
# product's "NO DATA" value and NaN/missing values mean the pixel has no
# observation at all. Eligible pixels are the observed pixels that can
# legitimately contribute to the coverage denominator BEFORE cloud-quality
# masking: cloudy/shadowed/defective pixels are eligible (they count as
# not valid), while no-data and missing pixels are excluded entirely
# because they carry no observation.
ELIGIBLE_SCL_CLASSES: tuple[int, ...] = tuple(range(1, 12))


def is_scl_class_usable(scl_class: int) -> bool:
    """Return True if an SCL class is accepted by the masking policy."""
    return scl_class in ACCEPTED_SCL_CLASSES


def is_scl_class_eligible(scl_class: Any) -> bool:
    """
    Return True if an SCL class represents an actual observation that may
    enter the coverage denominator (before cloud-quality masking).

    Classes 1..11 are eligible; class 0 (NO DATA), None and NaN are not.
    """
    if scl_class is None:
        return False
    try:
        if pd.isna(scl_class):
            return False
    except (TypeError, ValueError):
        pass
    return scl_class in ELIGIBLE_SCL_CLASSES


def compute_valid_pixel_fraction(
    valid_pixel_mean: Any,
    eligible_pixel_mean: Any,
) -> Optional[float]:
    """
    Calculate `valid_pixel_fraction = valid_pixels / eligible_pixels`.

    The two inputs are spatial means of a 0/1 flag band over the SAME
    parcel geometry on the SAME grid (both derived from the SCL band), so
    the ratio of the means equals the ratio of the pixel counts.

    Parameters
    ----------
    valid_pixel_mean : float or None
        Spatial mean of the valid flag band (1 = SCL class 4 or 5,
        0 = anything else) over the parcel.
    eligible_pixel_mean : float or None
        Spatial mean of the eligible flag band (1 = observed SCL class
        1..11, 0 = no data / missing) over the same parcel.

    Returns
    -------
    float in [0, 1], or None when the result is undefined:
    - None/NaN input (missing SCL information) -> None
    - eligible mean <= 0 (zero eligible pixels) -> None

    The result is clipped to [0, 1]; valid pixels are a subset of eligible
    pixels, so clipping only guards against floating-point round-off.
    """
    if valid_pixel_mean is None or eligible_pixel_mean is None:
        return None
    try:
        valid = float(valid_pixel_mean)
        eligible = float(eligible_pixel_mean)
    except (TypeError, ValueError):
        return None
    if pd.isna(valid) or pd.isna(eligible):
        return None
    if eligible <= 0:
        return None
    fraction = valid / eligible
    return float(min(1.0, max(0.0, fraction)))


def _extract_flag_series(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Normalize a raw openEO aggregate_spatial export to [date, value_col]."""
    out = df.copy()
    if value_col not in out.columns and "band_unnamed" in out.columns:
        out = out.rename(columns={"band_unnamed": value_col})
    if "date" not in out.columns or value_col not in out.columns:
        missing = {"date", value_col} - set(out.columns)
        raise ValueError(f"export missing columns {missing}")
    out["date"] = pd.to_datetime(out["date"], errors="coerce", utc=True)
    out = out.dropna(subset=["date"])
    out = out.drop_duplicates(subset=["date"], keep="first")
    return out[["date", value_col]]


def coverage_means_to_fraction(
    valid_df: pd.DataFrame,
    eligible_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combine the two raw coverage exports (spatial mean of the valid-flag
    band and of the eligible-flag band, as produced by openEO
    `aggregate_spatial` over the parcel) into one per-date series:

        date, valid_pixel_fraction

    Rows are matched on acquisition date with an inner join: a date present
    in only one input cannot produce a fraction. The fraction is computed
    with `compute_valid_pixel_fraction`, so zero eligible pixels or missing
    SCL information yield NaN (never a fabricated value), and every
    non-missing fraction lies in [0, 1].

    The result is sorted chronologically and deduplicated per date.
    """
    valid = _extract_flag_series(valid_df, "valid_pixel_mean")
    eligible = _extract_flag_series(eligible_df, "eligible_pixel_mean")

    merged = pd.merge(valid, eligible, on="date", how="inner")
    merged["valid_pixel_fraction"] = [
        compute_valid_pixel_fraction(v, e)
        for v, e in zip(merged["valid_pixel_mean"], merged["eligible_pixel_mean"])
    ]
    merged = merged.sort_values("date").reset_index(drop=True)
    return merged[["date", "valid_pixel_fraction"]]


def compute_ndvi(red: Optional[float], nir: Optional[float]) -> Optional[float]:
    """
    Compute NDVI = (NIR - RED) / (NIR + RED) with zero-denominator protection.

    Returns None when inputs are missing or the denominator is zero, so that
    an undefined ratio is never silently coerced to a number.
    """
    if red is None or nir is None or pd.isna(red) or pd.isna(nir):
        return None
    denominator = nir + red
    if denominator == 0:
        return None
    return (nir - red) / denominator


def evaluate_observation_quality(
    valid_pixel_fraction: Optional[float],
    min_valid_pixel_fraction: float = 0.50,
) -> tuple[bool, str]:
    """
    Evaluate if an individual observation meets pixel-quality requirements.

    Rule C: Observations with less than 50% valid pixels must not contribute
    as valid evidence.

    Parameters
    ----------
    valid_pixel_fraction : float or None
        Fraction of valid pixels in the parcel for this observation.
        Must be in [0, 1].
    min_valid_pixel_fraction : float
        Minimum acceptable fraction of valid pixels.

    Returns
    -------
    (is_usable, reason) : tuple
        is_usable is True if observation meets quality threshold.
        reason is a human-readable explanation for exclusion.
    """
    if valid_pixel_fraction is None or pd.isna(valid_pixel_fraction):
        return False, "Missing valid_pixel_fraction"

    if valid_pixel_fraction < 0 or valid_pixel_fraction > 1:
        return False, f"Invalid valid_pixel_fraction={valid_pixel_fraction:.4f} (must be in [0,1])"

    if valid_pixel_fraction < min_valid_pixel_fraction:
        return (
            False,
            f"valid_pixel_fraction={valid_pixel_fraction:.4f} < {min_valid_pixel_fraction:.2f}",
        )

    return True, "Meets pixel quality threshold"


def compute_temporal_coverage(
    acquisition_dates: list[datetime],
    window_start: datetime,
    window_end: datetime,
    interval_days: int = 10,
    min_observations_per_interval: int = 1,
) -> dict[str, Any]:
    """
    Compute temporal coverage of valid observations over a verification window.

    Temporal coverage = intervals_with_valid_observations / total_intervals
    where intervals are fixed consecutive calendar intervals of interval_days.

    Rule B: Less than 50% temporal coverage -> inconclusive.

    Parameters
    ----------
    acquisition_dates : list[datetime]
        List of acquisition datetimes (UTC) for valid observations.
        Duplicates in same interval are counted once.
    window_start : datetime
        Start of verification window (UTC).
    window_end : datetime
        End of verification window (UTC).
    interval_days : int
        Length of each interval in days (default 10).
    min_observations_per_interval : int
        Minimum observations to count interval as covered (default 1).

    Returns
    -------
    dict with:
        temporal_coverage: float in [0,1]
        total_intervals: int
        covered_intervals: int
        interval_length_days: int
        window_start: ISO format
        window_end: ISO format
    """
    if window_end <= window_start:
        return {
            "temporal_coverage": 0.0,
            "total_intervals": 0,
            "covered_intervals": 0,
            "interval_length_days": interval_days,
            "window_start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # Determine total number of intervals
    total_duration = (window_end - window_start).total_seconds()
    interval_seconds = interval_days * 86400
    if interval_seconds <= 0:
        total_intervals = 1
    else:
        # Ceiling division to ensure partial intervals are counted
        total_intervals = max(1, int((total_duration + interval_seconds - 1) // interval_seconds))

    # For each interval, check if it has >= min_observations
    covered_intervals = 0
    for i in range(total_intervals):
        interval_start = window_start + timedelta(days=i * interval_days)
        interval_end = window_start + timedelta(days=(i + 1) * interval_days)
        # Count observations that fall within this interval
        count_in_interval = sum(
            1 for d in acquisition_dates if interval_start <= d < interval_end
        )
        if count_in_interval >= min_observations_per_interval:
            covered_intervals += 1

    temporal_coverage = covered_intervals / total_intervals if total_intervals > 0 else 0.0

    return {
        "temporal_coverage": round(temporal_coverage, 4),
        "total_intervals": total_intervals,
        "covered_intervals": covered_intervals,
        "interval_length_days": interval_days,
        "window_start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def filter_observations_by_quality(
    df: pd.DataFrame,
    min_valid_pixel_fraction: float = 0.50,
    valid_fraction_col: str = "valid_pixel_fraction",
) -> dict[str, Any]:
    """
    Filter a DataFrame of observations by pixel quality.

    Preserves raw data semantics - marks observations as valid/invalid rather
    than deleting silently.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing observations with valid_pixel_fraction column.
    min_valid_pixel_fraction : float
        Minimum valid pixel fraction threshold.
    valid_fraction_col : str
        Column name for valid pixel fraction.

    Returns
    -------
    dict with:
        df_valid: DataFrame of observations meeting quality criteria
        df_invalid: DataFrame of observations failing quality criteria
        valid_count: int
        invalid_count: int
        excluded_reasons: list of reasons
    """
    df = df.copy()
    df["is_valid_observation"] = True
    df["quality_reason"] = None

    # Evaluate each observation
    for idx, row in df.iterrows():
        vpf = row.get(valid_fraction_col)
        is_usable, reason = evaluate_observation_quality(
            vpf, min_valid_pixel_fraction=min_valid_pixel_fraction
        )
        df.at[idx, "is_valid_observation"] = is_usable
        df.at[idx, "quality_reason"] = reason if not is_usable else None

    df_valid = df[df["is_valid_observation"]].copy()
    df_invalid = df[~df["is_valid_observation"]].copy()

    return {
        "df_valid": df_valid,
        "df_invalid": df_invalid,
        "valid_count": len(df_valid),
        "invalid_count": len(df_invalid),
        "excluded_reasons": df_invalid["quality_reason"].tolist() if len(df_invalid) > 0 else [],
    }


def merge_ndvi_and_coverage(
    ndvi_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    parcel_id: str,
) -> pd.DataFrame:
    """
    Merge a raw NDVI export and a valid-coverage export (as produced by
    openEO `aggregate_spatial`) into the standard Corina-facing schema:

        parcel_id, acquired_at, scene_id, ndvi_mean, valid_pixel_fraction

    Both inputs are expected to contain a `date` column and a value column.
    openEO typically names the aggregated value column `band_unnamed`; this is
    mapped to `ndvi_mean` / `valid_pixel_fraction` respectively.

    `scene_id` is not exposed by the aggregated export, so it is left as None
    rather than fabricated. Rows are matched on acquisition timestamp and
    sorted chronologically; rows present in only one input are dropped.
    """
    def _prepare(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
        out = df.copy()
        if value_col not in out.columns and "band_unnamed" in out.columns:
            out = out.rename(columns={"band_unnamed": value_col})
        if "date" in out.columns:
            out = out.rename(columns={"date": "acquired_at"})
        missing = {"acquired_at", value_col} - set(out.columns)
        if missing:
            raise ValueError(f"export missing columns {missing}")
        out["acquired_at"] = pd.to_datetime(
            out["acquired_at"], errors="coerce", utc=True
        )
        out = out.dropna(subset=["acquired_at"])
        return out[["acquired_at", value_col]]

    ndvi = _prepare(ndvi_df, "ndvi_mean")
    coverage = _prepare(coverage_df, "valid_pixel_fraction")

    merged = pd.merge(ndvi, coverage, on="acquired_at", how="inner")
    merged = merged.sort_values("acquired_at").reset_index(drop=True)

    merged.insert(0, "parcel_id", parcel_id)
    merged.insert(2, "scene_id", None)
    merged["acquired_at"] = merged["acquired_at"].dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    merged["ndvi_mean"] = merged["ndvi_mean"].astype(float).round(6)
    merged["valid_pixel_fraction"] = (
        merged["valid_pixel_fraction"].astype(float).round(4)
    )
    return merged[
        ["parcel_id", "acquired_at", "scene_id", "ndvi_mean", "valid_pixel_fraction"]
    ]
