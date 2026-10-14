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

from typing import Any, Optional

VERDICTS = {
    "CONFORM": "conform",
    "NONCONFORM": "nonconform",
    "INCONCLUSIVE": "inconclusive",
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
