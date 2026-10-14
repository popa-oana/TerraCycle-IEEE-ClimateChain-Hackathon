"""
test_rules.py — Testează verificatorul provizoriu de vegetație

Trei scenarii cu date sintetice (NU măsurători satelitare reale).

Rulare (din radacina repo-ului):
    .venv/Scripts/python.exe tests/test_rules.py
"""

import sys
from pathlib import Path

# Ancoram importul la radacina repo-ului, ca testul sa functioneze
# indiferent de directorul din care este rulat.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.rules import verify_vegetation

cases = {
    "vegetatie_clara": [0.5, 0.6, 0.7, 0.55, 0.65],
    "sol_nevegetat": [0.1, 0.2, 0.15, 0.18, 0.12],
    "date_insuficiente": [0.5, None, 0.6],
    "mixt_nonconform": [0.5, 0.1, 0.6, 0.1, 0.1],
    "valori_la_limita": [0.35, 0.35, 0.35, 0.35, 0.36],
    "cu_valori_invalide": [0.5, 0.6, None, 2.0, -1.5, 0.7, 0.8, 0.55],
}

print("=" * 60)
print("Test verificator provizoriu vegetatie")
print("=" * 60)

all_passed = True

for name, observations in cases.items():
    result = verify_vegetation(observations)
    print(f"\n--- {name} ---")
    print(f"  Observatii:       {observations}")
    print(f"  Verdict:          {result['verdict']}")
    print(f"  Motiv:            {result['reason']}")
    print(f"  Obs. valide:      {result['valid_observations']}")
    print(f"  Nr. vegetate:     {result['vegetated_count']}")
    print(f"  Fractie vegetata: {result['vegetated_fraction']}")

    # Verificări automate
    if name == "vegetatie_clara":
        assert result["verdict"] == "conform", \
            f"ESEC: asteptam conform, am primit {result['verdict']}"
    elif name == "sol_nevegetat":
        assert result["verdict"] == "nonconform", \
            f"ESEC: asteptam nonconform, am primit {result['verdict']}"
    elif name == "date_insuficiente":
        assert result["verdict"] == "inconclusive", \
            f"ESEC: asteptam inconclusive, am primit {result['verdict']}"
    elif name == "mixt_nonconform":
        assert result["verdict"] == "nonconform", \
            f"ESEC: asteptam nonconform, am primit {result['verdict']}"

print("\n" + "=" * 60)
print("Toate testele au trecut!")
print("=" * 60)
print("\nNOTA: Aceste date sunt sintetice, nu masuratori reale.")
print("Pragurile 0.35 si 0.80 sunt ipoteze experimentale.")
