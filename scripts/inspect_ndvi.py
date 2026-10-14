
"""
inspect_ndvi.py

Inspecteaza datele NDVI exportate din Copernicus Sentinel-2.

Functionalitati:
- Cauta automat exportul pentru sezonul complet.
- Daca nu exista, foloseste exportul pentru iunie.
- Verifica structura CSV.
- Converteste datele calendaristice.
- Sorteaza observatiile cronologic.
- Redenumeste coloana NDVI.
- Verifica valorile invalide si lipsa.
- Afiseaza statistici descriptive.
- Salveaza un CSV curatat.

Rulare din PowerShell (din radacina repo-ului):
    python scripts/inspect_ndvi.py
"""

import sys
from pathlib import Path

import pandas as pd


# Ancoram caile la radacina repo-ului, ca scriptul sa functioneze
# indiferent de directorul din care este rulat.
REPO_ROOT = Path(__file__).resolve().parents[1]


# ============================================================
# 1. CONFIGURARE
# ============================================================

DATA_DIR = REPO_ROOT / "data/ndvi"

# Preferam sezonul complet, apoi exportul de test.
CANDIDATES = [
    DATA_DIR / "parcel_01_2024.csv",
    DATA_DIR / "parcel_01_june_2024.csv",
]

OUTPUT_PATH = DATA_DIR / "parcel_01_clean.csv"


# ============================================================
# 2. GASIRE FISIER
# ============================================================

path = next(
    (candidate for candidate in CANDIDATES if candidate.exists()),
    None
)

if path is None:
    print("EROARE: Nu exista niciun CSV NDVI.")
    print("Ruleaza mai intai scripts/export_ndvi.py")
    sys.exit(1)

print(f"\nInspectez: {path}")


# ============================================================
# 3. CITIRE CSV
# ============================================================

try:
    df = pd.read_csv(path)
except Exception as error:
    print(f"EROARE la citirea CSV: {error}")
    sys.exit(1)

if df.empty:
    print("EROARE: CSV-ul este gol.")
    sys.exit(1)

print("\n=== COLOANE ORIGINALE ===")
print(df.columns.tolist())


# ============================================================
# 4. VALIDAREA STRUCTURII
# ============================================================

required_columns = [
    "date",
    "feature_index",
    "band_unnamed",
]

missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]

if missing_columns:
    print("EROARE: Lipsesc coloanele:", missing_columns)
    sys.exit(1)

# Pentru primul export lucram cu o singura parcela.
if df["feature_index"].nunique() != 1:
    print("EROARE: CSV-ul contine mai multe parcele.")
    sys.exit(1)


# ============================================================
# 5. REDENUMIRE COLOANE
# ============================================================

df = df.rename(
    columns={
        "band_unnamed": "ndvi_mean"
    }
)


# ============================================================
# 6. CONVERSIE TIPURI
# ============================================================

df["date"] = pd.to_datetime(
    df["date"],
    errors="coerce",
    utc=True
)

df["ndvi_mean"] = pd.to_numeric(
    df["ndvi_mean"],
    errors="coerce"
)


# ============================================================
# 7. VERIFICAREA CALITATII
# ============================================================

print("\n=== VALORI LIPSA ===")
print(df.isna().sum())

invalid_dates = df["date"].isna().sum()

invalid_ndvi = (
    df["ndvi_mean"].notna()
    & ~df["ndvi_mean"].between(-1, 1)
).sum()

print("\n=== VERIFICARI ===")
print("Date invalide:", invalid_dates)
print("NDVI in afara intervalului [-1, 1]:", invalid_ndvi)

# Elimina randurile cu date lipsa sau valori invalide.
initial_rows = len(df)

df = df.dropna(
    subset=["date", "ndvi_mean"]
)

df = df[
    df["ndvi_mean"].between(-1, 1)
].copy()

# Sortare cronologica.
df = df.sort_values("date")

# Eliminam duplicatele pentru aceeasi parcela si data.
df = df.drop_duplicates(
    subset=["date", "feature_index"],
    keep="first"
)

df = df.reset_index(drop=True)

print("Randuri initiale:", initial_rows)
print("Randuri valide:", len(df))
print("Randuri eliminate:", initial_rows - len(df))

if df.empty:
    print("EROARE: Nu au ramas observatii valide.")
    sys.exit(1)


# ============================================================
# 8. AFISAREA OBSERVATIILOR
# ============================================================

print("\n=== OBSERVATII NDVI CRONOLOGICE ===")

print(
    df[
        ["date", "feature_index", "ndvi_mean"]
    ].to_string(index=False)
)


# ============================================================
# 9. STATISTICI DESCRIPTIVE
# ============================================================

print("\n=== STATISTICI NDVI ===")

print("Numar observatii:", len(df))
print("NDVI minim:", round(df["ndvi_mean"].min(), 4))
print("NDVI maxim:", round(df["ndvi_mean"].max(), 4))
print("NDVI mediu:", round(df["ndvi_mean"].mean(), 4))
print("NDVI median:", round(df["ndvi_mean"].median(), 4))
print("Deviatie standard:", round(df["ndvi_mean"].std(), 4))

print("\nPrima observatie:", df["date"].min())
print("Ultima observatie:", df["date"].max())


# ============================================================
# 10. EXPORT DATE CURATATE
# ============================================================

df.to_csv(
    OUTPUT_PATH,
    index=False,
    date_format="%Y-%m-%dT%H:%M:%SZ"
)

print("\n=== EXPORT FINAL ===")
print("CSV curatat salvat la:", OUTPUT_PATH)
print("Procesare finalizata cu succes!")
