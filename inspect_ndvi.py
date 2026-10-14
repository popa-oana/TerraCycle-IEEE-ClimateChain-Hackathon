"""
inspect_ndvi.py — Inspectează CSV-ul exportat de la Copernicus

Afișează structura, primele rânduri, valorile lipsă și
tipurile de date pentru a verifica corectitudinea exportului.

Rulare:
    .\.venv\Scripts\python.exe inspect_ndvi.py
"""

import sys
from pathlib import Path

import pandas as pd

# Caută mai întâi fișierul de test (o lună), apoi cel complet
candidates = [
    Path("data/ndvi/parcel_01_june_2024.csv"),
    Path("data/ndvi/parcel_01_2024.csv"),
]

path = None
for candidate in candidates:
    if candidate.exists():
        path = candidate
        break

if path is None:
    print("EROARE: Nu exista niciun CSV NDVI in data/ndvi/")
    print("Ruleaza mai intai export_ndvi.py")
    sys.exit(1)

print(f"Inspectez: {path}\n")

df = pd.read_csv(path)

print("=== COLOANE ===")
print(df.columns.tolist())

print("\n=== PRIMELE 10 RANDURI ===")
print(df.head(10).to_string(index=False))

print(f"\n=== DIMENSIUNE ===")
print(f"Randuri: {len(df)}")
print(f"Coloane: {len(df.columns)}")

print("\n=== VALORI LIPSA ===")
print(df.isna().sum())

print("\n=== TIPURI DE DATE ===")
print(df.dtypes)

print("\n=== STATISTICI DESCRIPTIVE ===")
# Afișăm statisticile doar pentru coloanele numerice
numeric_cols = df.select_dtypes(include="number")
if not numeric_cols.empty:
    print(numeric_cols.describe().to_string())
else:
    print("Nu au fost gasite coloane numerice.")
