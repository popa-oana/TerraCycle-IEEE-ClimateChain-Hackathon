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
        Verification policy containing at minimum:
            - ndvi_threshold (float, default 0.35)
            - required_fraction (float, default 0.80)
            - min_observations (int, default 5)
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
            "quality": {
                "valid_count": 0,
                "total_rows": 0,
                "excluded_count": 0,
                "inconclusive_reason": "MISSING_EVIDENCE",
            },
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
            "quality": {
                "valid_count": 0,
                "total_rows": 0,
                "excluded_count": 0,
                "inconclusive_reason": "CSV_READ_ERROR",
            },
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
            "quality": {
                "valid_count": 0,
                "total_rows": len(df),
                "excluded_count": len(df),
                "inconclusive_reason": "INVALID_CSV_STRUCTURE",
            },
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
    df = df.drop_duplicates(subset=["date"], keep="first")

    excluded_count = total_rows - len(df)

    # --- Extract NDVI values ---
    ndvi_values = df["ndvi_mean"].tolist()

    # --- Build observations list ---
    observations_list = []
    for _, row in df.iterrows():
        obs = {
            "acquired_at": row["date"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ndvi_mean": round(float(row["ndvi_mean"]), 6),
        }
        if "valid_pixel_fraction" in df.columns:
            obs["valid_pixel_fraction"] = round(
                float(row["valid_pixel_fraction"]), 4
            )
        observations_list.append(obs)

    # --- Apply verification rules ---
    ndvi_threshold = policy.get("ndvi_threshold", 0.35)
    required_fraction = policy.get("required_fraction", 0.80)
    min_observations = policy.get("min_observations", 5)

    result = verify_vegetation(
        observations=ndvi_values,
        min_observations=min_observations,
        ndvi_threshold=ndvi_threshold,
        required_fraction=required_fraction,
    )

    verdict = result["verdict"]

    return {
        "verdict": verdict,
        "verdict_code": VERDICT_CODES[verdict],
        "reason_code": (
            "INSUFFICIENT_OBSERVATIONS"
            if verdict == "inconclusive"
            else "RULE_BASED_DECISION"
        ),
        "reason": result["reason"],
        "observations": observations_list,
        "quality": {
            "valid_count": result["valid_observations"],
            "total_rows": total_rows,
            "excluded_count": excluded_count,
            "vegetated_count": result["vegetated_count"],
            "vegetated_fraction": result["vegetated_fraction"],
            "inconclusive_reason": (
                "INSUFFICIENT_OBSERVATIONS"
                if verdict == "inconclusive"
                else None
            ),
        },
        "model": {
            "model_version": "rule-based-v1",
            "features_version": None,
            "source": "RULE_BASED",
            "thresholds": result["thresholds"],
        },
        "source": {
            "provider": "Copernicus Data Space",
            "dataset": "Sentinel-2 L2A",
            "method": "cloud-masked NDVI (SCL classes 4,5)",
            "csv_file": str(csv_path),
        },
    }

