"""
backend/ml/rules.py — Verificator provizoriu de vegetație

Funcția verify_vegetation() primește o listă de valori NDVI
și returnează un verdict: conform, nonconform sau inconclusive.

ATENȚIE: Pragurile 0.35 (NDVI) și 0.80 (fracție) sunt
ipoteze de lucru demonstrative, NU criterii agronomice validate.
Acest verificator NU emite un verdict agricol definitiv.

Funcția finală va trebui să primească și:
  - perioada angajamentului (window_start, window_end)
  - datele de achiziție ale observațiilor
  - fracția pixelilor valizi pentru fiecare observație
  - acoperirea temporală

Corina importă direct această funcție în backend.
Nu se scrie un al doilea algoritm de verificare în FastAPI.

Interfața conform TerraCycle_Ghid_Integrare.md §7:
  verify_parcel(parcel_id, policy, evidence_directory) -> dict
  (va fi implementată complet după etapa de etichetare)
"""

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from backend.ml.quality import (
    compute_temporal_coverage,
    evaluate_observation_quality,
)

VERDICTS = {
    "CONFORM": "conform",
    "NONCONFORM": "nonconform",
    "INCONCLUSIVE": "inconclusive",
}

# Verdict codes for EIP-712/Solidity (Agent.md §4)
VERDICT_CODES = {
    "conform": 0,
    "nonconform": 1,
    "inconclusive": 2,
}


def _no_evidence_quality(
    reason_code: str,
    total_rows: int = 0,
    excluded_count: int = 0,
) -> dict[str, Any]:
    """
    Build a consistent `quality` block for responses that never reached the
    observation-level analysis (missing file, read error, bad structure).

    Keeping the same keys as the full pipeline lets downstream consumers
    (e.g. Corina's backend) parse every response uniformly.
    """
    return {
        "valid_count": 0,
        "total_rows": total_rows,
        "excluded_count": excluded_count,
        "structural_excluded_count": excluded_count,
        "quality_excluded_count": 0,
        "quality_metadata_available": False,
        "evidence_quality": "unknown",
        "min_valid_pixel_fraction": None,
        "temporal_coverage": None,
        "covered_intervals": None,
        "total_intervals": None,
        "interval_length_days": None,
        "inconclusive_reason": reason_code,
        "warnings": [f"No usable evidence ({reason_code})"],
    }


def verify_vegetation(
    observations: list[Optional[float]],
    min_observations: int = 5,
    ndvi_threshold: float = 0.35,
    required_fraction: float = 0.80,
) -> dict[str, Any]:
    """
    Verificator demonstrativ de vegetație bazat pe NDVI.

    Parametri
    ---------
    observations : list[Optional[float]]
        Lista valorilor medii NDVI pentru fiecare observație.
        Valorile None sau în afara [-1, 1] sunt ignorate.
    min_observations : int
        Numărul minim de observații valide necesar pentru un verdict.
    ndvi_threshold : float
        Pragul NDVI peste care o observație e considerată vegetată.
    required_fraction : float
        Fracția minimă de observații vegetate pentru verdict conform.

    Returnează
    ----------
    dict cu:
        verdict: "conform" | "nonconform" | "inconclusive"
        reason: explicația verdictului
        valid_observations: câte observații valide au fost
        vegetated_count: câte depășesc pragul
        vegetated_fraction: fracția observațiilor vegetate
        thresholds: pragurile folosite (pentru reproductibilitate)
    """
    # Filtrăm observațiile invalide
    valid = [
        x for x in observations
        if x is not None and -1 <= x <= 1
    ]

    thresholds = {
        "ndvi_threshold": ndvi_threshold,
        "required_fraction": required_fraction,
        "min_observations": min_observations,
    }

    if len(valid) < min_observations:
        return {
            "verdict": VERDICTS["INCONCLUSIVE"],
            "reason": "Insufficient valid NDVI observations",
            "valid_observations": len(valid),
            "vegetated_count": 0,
            "vegetated_fraction": 0.0,
            "thresholds": thresholds,
        }

    count_vegetated = sum(
        value > ndvi_threshold for value in valid
    )
    fraction = count_vegetated / len(valid)

    verdict = (
        VERDICTS["CONFORM"]
        if fraction >= required_fraction
        else VERDICTS["NONCONFORM"]
    )

    return {
        "verdict": verdict,
        "reason": (
            f"{count_vegetated}/{len(valid)} observations above "
            f"NDVI threshold {ndvi_threshold} "
            f"(fraction={fraction:.2f}, required={required_fraction})"
        ),
        "valid_observations": len(valid),
        "vegetated_count": count_vegetated,
        "vegetated_fraction": round(fraction, 4),
        "thresholds": thresholds,
    }


def verify_parcel(
    parcel_id: str,
    policy: dict[str, Any],
    evidence_directory: str,
) -> dict[str, Any]:
    """
    Integration interface for Corina's FastAPI backend.
    Signature matches TerraCycle_Ghid_Integrare.md §7.

    Loads NDVI CSV from evidence_directory, validates data,
    applies the provisional rule-based verifier, and returns
    the verdict with observations and quality metadata.

    This function does NOT sign or hash the result.
    Corina's backend handles canonical serialization and SHA-256.

    Parameters
    ----------
    parcel_id : str
        The parcel identifier (e.g., "parcel_01").
    policy : dict[str, Any]
        Verification policy. Recognised keys:
            - ndvi_threshold (float, default 0.35)
            - required_fraction (float, default 0.80)
            - min_observations (int, default 5)
            - min_valid_pixel_fraction (float, default 0.50)  [Rule C]
            - min_temporal_coverage (float, default 0.50)     [Rule B]
            - temporal_coverage_interval_days (int, default 10) [Rule B]
            - window_start (ISO date/str, optional)          [Rule B]
            - window_end (ISO date/str, optional, exclusive) [Rule B]
        Rule B is only enforced when both window_start and window_end are given.
        Rule C is only enforced when the CSV contains a valid_pixel_fraction column.
    evidence_directory : str
        Path to the directory containing NDVI CSV files.

    Returns
    -------
    dict with:
        verdict: "conform" | "nonconform" | "inconclusive"
        verdict_code: 0 | 1 | 2
        reason_code: str
        reason: str
        observations: list of observation dicts
        quality: dict with observation counts and coverage info
        model: dict with verifier version metadata
        source: dict with data provenance
    """
    evidence_dir = Path(evidence_directory)

    # --- Locate CSV file ---
    # Prefer full-season, then June-only
    csv_candidates = [
        evidence_dir / f"{parcel_id}_2024.csv",
        evidence_dir / f"{parcel_id}_june_2024.csv",
        evidence_dir / f"{parcel_id}_clean.csv",
    ]

    csv_path = next(
        (p for p in csv_candidates if p.exists() and p.stat().st_size > 0),
        None,
    )

    if csv_path is None:
        return {
            "verdict": VERDICTS["INCONCLUSIVE"],
            "verdict_code": VERDICT_CODES["inconclusive"],
            "reason_code": "MISSING_EVIDENCE",
            "reason": f"No NDVI CSV found for {parcel_id} in {evidence_directory}",
            "observations": [],
            "quality": _no_evidence_quality("MISSING_EVIDENCE"),
            "model": {
                "model_version": "rule-based-v1",
                "source": "RULE_BASED",
            },
            "source": {
                "provider": "Copernicus Data Space",
                "dataset": "Sentinel-2 L2A",
                "csv_file": None,
            },
        }

    # --- Load CSV ---
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        return {
            "verdict": VERDICTS["INCONCLUSIVE"],
            "verdict_code": VERDICT_CODES["inconclusive"],
            "reason_code": "CSV_READ_ERROR",
            "reason": f"Failed to read CSV: {exc}",
            "observations": [],
            "quality": _no_evidence_quality("CSV_READ_ERROR"),
            "model": {
                "model_version": "rule-based-v1",
                "source": "RULE_BASED",
            },
            "source": {
                "provider": "Copernicus Data Space",
                "dataset": "Sentinel-2 L2A",
                "csv_file": str(csv_path),
            },
        }

    # --- Validate and normalize columns ---
    if "band_unnamed" in df.columns:
        df = df.rename(columns={"band_unnamed": "ndvi_mean"})

    required_cols = {"date", "ndvi_mean"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        return {
            "verdict": VERDICTS["INCONCLUSIVE"],
            "verdict_code": VERDICT_CODES["inconclusive"],
            "reason_code": "INVALID_CSV_STRUCTURE",
            "reason": f"CSV missing required columns: {missing_cols}",
            "observations": [],
            "quality": _no_evidence_quality(
                "INVALID_CSV_STRUCTURE",
                total_rows=len(df),
                excluded_count=len(df),
            ),
            "model": {
                "model_version": "rule-based-v1",
                "source": "RULE_BASED",
            },
            "source": {
                "provider": "Copernicus Data Space",
                "dataset": "Sentinel-2 L2A",
                "csv_file": str(csv_path),
            },
        }

    total_rows = len(df)

    # Convert timestamps
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
    df["ndvi_mean"] = pd.to_numeric(df["ndvi_mean"], errors="coerce")

    # Drop rows with missing date or ndvi_mean
    df = df.dropna(subset=["date", "ndvi_mean"])

    # Filter NDVI to valid range [-1, 1]
    df = df[df["ndvi_mean"].between(-1, 1)].copy()

    # Sort chronologically
    df = df.sort_values("date").reset_index(drop=True)

    # Remove duplicate dates (keep first)
    df = df.drop_duplicates(subset=["date"], keep="first").reset_index(drop=True)

    structural_excluded = total_rows - len(df)

    # --- Policy parameters ---
    ndvi_threshold = policy.get("ndvi_threshold", 0.35)
    required_fraction = policy.get("required_fraction", 0.80)
    min_observations = policy.get("min_observations", 5)
    min_valid_pixel_fraction = policy.get("min_valid_pixel_fraction", 0.50)
    min_temporal_coverage = policy.get("min_temporal_coverage", 0.50)
    interval_days = policy.get("temporal_coverage_interval_days", 10)
    window_start_raw = policy.get("window_start")
    window_end_raw = policy.get("window_end")

    # --- Rule C: pixel quality filtering ---
    # The rule is only applied when valid_pixel_fraction is present. When it is
    # missing entirely, observations are NOT treated as fully validated evidence:
    # their evidence quality is reported as "unknown" (see quality metadata below).
    has_quality_col = "valid_pixel_fraction" in df.columns
    if has_quality_col:
        df["valid_pixel_fraction"] = pd.to_numeric(
            df["valid_pixel_fraction"], errors="coerce"
        )
        quality_metadata_available = bool(
            df["valid_pixel_fraction"].notna().any()
        )
    else:
        quality_metadata_available = False

    # --- Build observations list and apply Rule C ---
    observations_list: list[dict[str, Any]] = []
    valid_ndvi_values: list[float] = []
    valid_dates: list[Any] = []
    quality_excluded = 0

    for _, row in df.iterrows():
        row_vpf = row["valid_pixel_fraction"] if has_quality_col else None
        if has_quality_col:
            is_valid, reason = evaluate_observation_quality(
                row_vpf, min_valid_pixel_fraction=min_valid_pixel_fraction
            )
        else:
            # No quality metadata: do not reject here, but flag evidence quality.
            is_valid, reason = True, None

        obs: dict[str, Any] = {
            "acquired_at": row["date"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ndvi_mean": round(float(row["ndvi_mean"]), 6),
            "is_valid_observation": bool(is_valid),
        }
        if has_quality_col and pd.notna(row_vpf):
            obs["valid_pixel_fraction"] = round(float(row_vpf), 4)
        if not is_valid:
            obs["quality_reason"] = reason
            quality_excluded += 1
        observations_list.append(obs)

        if is_valid:
            valid_ndvi_values.append(float(row["ndvi_mean"]))
            valid_dates.append(row["date"].to_pydatetime())

    # --- Rule B: temporal coverage (only when a window is specified) ---
    temporal: Optional[dict[str, Any]] = None
    if window_start_raw and window_end_raw:
        try:
            window_start = pd.to_datetime(window_start_raw, utc=True).to_pydatetime()
            window_end = pd.to_datetime(window_end_raw, utc=True).to_pydatetime()
            in_window = [
                d for d in valid_dates if window_start <= d < window_end
            ]
            temporal = compute_temporal_coverage(
                in_window,
                window_start,
                window_end,
                interval_days=interval_days,
            )
        except Exception:
            temporal = None

    # --- Apply experimental vegetation classification on quality-valid data ---
    result = verify_vegetation(
        observations=valid_ndvi_values,
        min_observations=min_observations,
        ndvi_threshold=ndvi_threshold,
        required_fraction=required_fraction,
    )

    verdict = result["verdict"]
    if verdict == VERDICTS["INCONCLUSIVE"]:
        reason_code = "INSUFFICIENT_OBSERVATIONS"
    else:
        reason_code = "RULE_BASED_DECISION"
    reason = result["reason"]

    # --- Rule B enforcement: insufficient temporal coverage => inconclusive ---
    if (
        temporal is not None
        and verdict != VERDICTS["INCONCLUSIVE"]
        and temporal["temporal_coverage"] < min_temporal_coverage
    ):
        verdict = VERDICTS["INCONCLUSIVE"]
        reason_code = "INSUFFICIENT_TEMPORAL_COVERAGE"
        reason = (
            f"Temporal coverage {temporal['temporal_coverage']:.2f} < "
            f"required {min_temporal_coverage:.2f} "
            f"({temporal['covered_intervals']}/{temporal['total_intervals']} "
            f"intervals of {interval_days} days)"
        )

    # --- Evidence-quality reporting ---
    warnings: list[str] = []
    if not quality_metadata_available:
        warnings.append(
            "valid_pixel_fraction missing; pixel-quality rule (Rule C) not applied"
        )
    if temporal is None:
        warnings.append(
            "window_start/window_end not provided; temporal-coverage rule (Rule B) not applied"
        )

    thresholds = {
        "ndvi_threshold": ndvi_threshold,
        "required_fraction": required_fraction,
        "min_observations": min_observations,
        "min_valid_pixel_fraction": min_valid_pixel_fraction,
        "min_temporal_coverage": min_temporal_coverage,
        "temporal_coverage_interval_days": interval_days,
        "window_start": window_start_raw,
        "window_end": window_end_raw,
    }

    quality: dict[str, Any] = {
        "valid_count": len(valid_ndvi_values),
        "total_rows": total_rows,
        "excluded_count": total_rows - len(valid_ndvi_values),
        "structural_excluded_count": structural_excluded,
        "quality_excluded_count": quality_excluded,
        "vegetated_count": result["vegetated_count"],
        "vegetated_fraction": result["vegetated_fraction"],
        "quality_metadata_available": quality_metadata_available,
        "evidence_quality": (
            "assessed" if quality_metadata_available else "unknown"
        ),
        "min_valid_pixel_fraction": min_valid_pixel_fraction,
        "temporal_coverage": (
            temporal["temporal_coverage"] if temporal is not None else None
        ),
        "covered_intervals": (
            temporal["covered_intervals"] if temporal is not None else None
        ),
        "total_intervals": (
            temporal["total_intervals"] if temporal is not None else None
        ),
        "interval_length_days": (
            temporal["interval_length_days"] if temporal is not None else None
        ),
        "inconclusive_reason": (
            reason_code if verdict == VERDICTS["INCONCLUSIVE"] else None
        ),
        "warnings": warnings,
    }

    return {
        "verdict": verdict,
        "verdict_code": VERDICT_CODES[verdict],
        "reason_code": reason_code,
        "reason": reason,
        "observations": observations_list,
        "quality": quality,
        "model": {
            "model_version": "rule-based-v1",
            "features_version": None,
            "source": "RULE_BASED",
            "thresholds": thresholds,
        },
        "source": {
            "provider": "Copernicus Data Space",
            "dataset": "Sentinel-2 L2A",
            "method": "cloud-masked NDVI (SCL classes 4,5)",
            "csv_file": str(csv_path),
        },
    }

