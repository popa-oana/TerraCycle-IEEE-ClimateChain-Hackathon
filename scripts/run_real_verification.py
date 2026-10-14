"""
run_real_verification.py — Pipeline de verificare provizorie pe date reale

Citește CSV-ul NDVI exportat din Copernicus Sentinel-2,
validează datele, aplică verificatorul provizoriu din
backend/ml/rules.py și salvează rezultatul JSON.

ATENȚIE: Rezultatul este EXPERIMENTAL. Nu reprezintă un
verdict agronomic validat și nu autorizează plăți on-chain.

Rulare (din radacina repo-ului):
    .venv/Scripts/python.exe scripts/run_real_verification.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Ancoram importurile si caile la radacina repo-ului, ca scriptul sa
# functioneze indiferent de directorul din care este rulat.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.rules import verify_vegetation, VERDICT_CODES

# ============================================================
# 1. CONFIGURATION
# ============================================================

PARCEL_ID = "parcel_01"
DATA_DIR = REPO_ROOT / "data/ndvi"
OUTPUT_DIR = REPO_ROOT / "data/features"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_JSON = OUTPUT_DIR / f"{PARCEL_ID}_provisional_result.json"

# CSV candidates in priority order
CSV_CANDIDATES = [
    DATA_DIR / f"{PARCEL_ID}_2024.csv",        # full season preferred
    DATA_DIR / f"{PARCEL_ID}_june_2024.csv",    # June-only fallback
]


# ============================================================
# 2. FIND AVAILABLE CSV
# ============================================================

def find_csv():
    """Find the best available NDVI CSV file."""
    for candidate in CSV_CANDIDATES:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None


csv_path = find_csv()

if csv_path is None:
    print("EROARE: Nu s-a gasit niciun fisier CSV NDVI.")
    print("Fisiere cautate:")
    for c in CSV_CANDIDATES:
        print(f"  {c} — {'exista' if c.exists() else 'NU exista'}")
    print("\nRuleaza mai intai scripts/export_ndvi.py pentru a exporta date.")
    sys.exit(1)

# Cale relativa la repo, pentru un output portabil (fara cai absolute).
try:
    SOURCE_FILE = csv_path.relative_to(REPO_ROOT).as_posix()
except ValueError:
    SOURCE_FILE = str(csv_path)

print("=" * 70)
print("TERRACYCLE PROOF - VERIFICARE PROVIZORIE PE DATE REALE")
print("=" * 70)
print(f"\nFisier sursa: {SOURCE_FILE}")


# ============================================================
# 3. READ CSV
# ============================================================

try:
    df = pd.read_csv(csv_path)
except Exception as error:
    print(f"EROARE la citirea CSV: {error}")
    sys.exit(1)

print(f"Randuri citite:  {len(df)}")
print(f"Coloane:         {df.columns.tolist()}")


# ============================================================
# 4. VALIDATE COLUMNS
# ============================================================

# Rename band_unnamed -> ndvi_mean if present
if "band_unnamed" in df.columns:
    df = df.rename(columns={"band_unnamed": "ndvi_mean"})
    print("\nColoana 'band_unnamed' redenumita in 'ndvi_mean'.")

required_columns = ["date", "ndvi_mean"]
missing = [c for c in required_columns if c not in df.columns]

if missing:
    print(f"EROARE: Lipsesc coloanele: {missing}")
    print(f"Coloane disponibile: {df.columns.tolist()}")
    sys.exit(1)

print(f"Coloane dupa redenumire: {df.columns.tolist()}")


# ============================================================
# 5. CONVERT TIMESTAMPS
# ============================================================

df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
invalid_dates = df["date"].isna().sum()
print(f"\nDate calendaristice invalide: {invalid_dates}")


# ============================================================
# 6. CONVERT NDVI VALUES
# ============================================================

df["ndvi_mean"] = pd.to_numeric(df["ndvi_mean"], errors="coerce")
missing_ndvi = df["ndvi_mean"].isna().sum()
print(f"Valori NDVI lipsa/invalide: {missing_ndvi}")


# ============================================================
# 7. DATA QUALITY CHECKS
# ============================================================

initial_rows = len(df)

# Drop rows with missing date or NDVI
df = df.dropna(subset=["date", "ndvi_mean"])

# Validate NDVI range [-1, 1]
out_of_range = (~df["ndvi_mean"].between(-1, 1)).sum()
if out_of_range > 0:
    print(f"Valori NDVI in afara [-1, 1]: {out_of_range}")
df = df[df["ndvi_mean"].between(-1, 1)].copy()

# Sort chronologically
df = df.sort_values("date").reset_index(drop=True)

# Check for duplicates
duplicates = df.duplicated(subset=["date"], keep="first").sum()
if duplicates > 0:
    print(f"Duplicate gasite (acelasi timestamp): {duplicates}")
df = df.drop_duplicates(subset=["date"], keep="first")

final_rows = len(df)
excluded = initial_rows - final_rows

print(f"\nRanduri initiale:  {initial_rows}")
print(f"Randuri valide:    {final_rows}")
print(f"Randuri excluse:   {excluded}")

if df.empty:
    print("\nEROARE: Nu au ramas observatii valide dupa filtrare.")
    sys.exit(1)


# ============================================================
# 8. PARCEL IDENTIFICATION
# ============================================================

# The CSV from openEO uses feature_index for parcel reference
if "feature_index" in df.columns:
    unique_features = df["feature_index"].nunique()
    print(f"\nParcele in CSV (feature_index): {unique_features}")
    if unique_features > 1:
        print("ATENTIE: CSV-ul contine mai multe parcele!")

print(f"Parcela tinta: {PARCEL_ID}")


# ============================================================
# 9. DISPLAY OBSERVATIONS
# ============================================================

print("\n" + "=" * 70)
print("OBSERVATII NDVI CRONOLOGICE (date reale Copernicus)")
print("=" * 70)

for idx, row in df.iterrows():
    date_str = row["date"].strftime("%Y-%m-%d")
    ndvi = row["ndvi_mean"]
    # Visual indicator
    bar_len = max(0, int(ndvi * 40))
    bar = "#" * bar_len
    print(f"  {date_str}  NDVI={ndvi:.4f}  {bar}")


# ============================================================
# 10. DESCRIPTIVE STATISTICS
# ============================================================

print("\n" + "-" * 40)
print("STATISTICI")
print("-" * 40)
print(f"  Numar observatii:    {len(df)}")
print(f"  NDVI minim:          {df['ndvi_mean'].min():.4f}")
print(f"  NDVI maxim:          {df['ndvi_mean'].max():.4f}")
print(f"  NDVI mediu:          {df['ndvi_mean'].mean():.4f}")
print(f"  NDVI median:         {df['ndvi_mean'].median():.4f}")
print(f"  Deviatie standard:   {df['ndvi_mean'].std():.4f}")
print(f"  Prima observatie:    {df['date'].min().strftime('%Y-%m-%d')}")
print(f"  Ultima observatie:   {df['date'].max().strftime('%Y-%m-%d')}")


# ============================================================
# 11. RUN PROVISIONAL VERIFIER
# ============================================================

print("\n" + "=" * 70)
print("VERIFICARE PROVIZORIE")
print("=" * 70)

ndvi_values = df["ndvi_mean"].tolist()

result = verify_vegetation(
    observations=ndvi_values,
    min_observations=5,
    ndvi_threshold=0.35,
    required_fraction=0.80,
)

verdict = result["verdict"]
verdict_code = VERDICT_CODES[verdict]

print(f"\n  VERDICT:             {verdict.upper()}")
print(f"  Cod verdict:         {verdict_code}")
print(f"  Motiv:               {result['reason']}")
print(f"  Observatii valide:   {result['valid_observations']}")
print(f"  Nr. vegetate:        {result['vegetated_count']}")
print(f"  Fractie vegetata:    {result['vegetated_fraction']}")


# ============================================================
# 12. BUILD OBSERVATIONS LIST FOR JSON
# ============================================================

observations_list = []
for _, row in df.iterrows():
    obs = {
        "acquired_at": row["date"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ndvi_mean": round(float(row["ndvi_mean"]), 6),
    }
    observations_list.append(obs)


# ============================================================
# 13. SAVE JSON RESULT
# ============================================================

output_data = {
    "parcel_id": PARCEL_ID,
    "source_file": SOURCE_FILE,
    "observation_count": len(df),
    "first_observation": df["date"].min().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "last_observation": df["date"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "result": {
        "verdict": result["verdict"],
        "verdict_code": verdict_code,
        "reason": result["reason"],
        "valid_observations": result["valid_observations"],
        "vegetated_count": result["vegetated_count"],
        "vegetated_fraction": result["vegetated_fraction"],
        "thresholds": result["thresholds"],
    },
    "validation_status": "experimental_only",
    "limitations": [
        "Pixel validity fraction (valid_pixel_fraction) is not available in the current CSV.",
        "Complete temporal coverage has not been validated.",
        "The demonstration polygon may include multiple agricultural fields.",
        "Experimental NDVI thresholds (0.35) and fraction requirements (0.80) are not agronomically validated.",
        "Manual labels have not yet been collected.",
        "LightGBM has not been trained.",
        "NDVI alone cannot demonstrate absence of herbicides, compliance with fertilization rules, or organic certification.",
        "This provisional result must NOT authorize blockchain settlement or on-chain payments.",
    ],
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "model_version": "rule-based-v1",
    "data_source": {
        "provider": "Copernicus Data Space",
        "dataset": "Sentinel-2 L2A",
        "bands": ["B04", "B08", "SCL"],
        "method": "cloud-masked NDVI mean (SCL classes 4,5 retained)",
    },
}

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

print(f"\n  JSON salvat:         {OUTPUT_JSON}")


# ============================================================
# 14. FINAL DISCLAIMER
# ============================================================

print("\n" + "=" * 70)
print("DISCLAIMER")
print("=" * 70)
print("""
  Acest rezultat este EXPERIMENTAL (validation_status: experimental_only).
  
  NU reprezinta:
  - Un verdict agronomic validat
  - O certificare bio sau de sustenabilitate
  - O autorizare pentru plati on-chain
  
  Pragurile NDVI si fractiile sunt ipoteze de lucru demonstrative.
  Verificarea completa necesita: coverage temporal, valid_pixel_fraction,
  etichete manuale, model LightGBM si evaluare fara data leakage.
""")
print("Procesare finalizata cu succes!")
