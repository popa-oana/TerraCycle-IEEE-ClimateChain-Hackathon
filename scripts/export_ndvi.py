r"""
export_ndvi.py — Extrage seria temporală NDVI din Sentinel-2 via openEO

Fluxul:
  1. Citește parcela din data/parcels/parcel_01.geojson
  2. Se autentifică la Copernicus Data Space (openEO)
  3. Încarcă colecția SENTINEL2_L2A cu benzile B04, B08, SCL
  4. Calculează NDVI = (B08 - B04) / (B08 + B04)
  5. Construiește masca de nori din SCL (păstrează doar clasele 4 și 5)
  6. Aplică masca pe NDVI
  7. Agregare spațială (media) pe suprafața parcelei
  8. Lansează batch job și descarcă rezultatul CSV

Bazat pe notebook-ul oficial Copernicus:
  https://documentation.dataspace.copernicus.eu/notebook-samples/openeo/NDVI_Timeseries.html

Rulare (din radacina repo-ului):
    .\.venv\Scripts\python.exe scripts\export_ndvi.py

Notă: Jobul poate dura câteva minute. Mesajele "Job running"
sunt normale.
"""

import json
import sys
from pathlib import Path

import openeo

# Ancoram caile la radacina repo-ului, ca scriptul sa functioneze
# indiferent de directorul din care este rulat.
REPO_ROOT = Path(__file__).resolve().parents[1]

# ─── 1. Pregătim directoarele ───────────────────────────────────────
output_dir = REPO_ROOT / "data/ndvi"
output_dir.mkdir(parents=True, exist_ok=True)

# ─── 2. Citim parcela ──────────────────────────────────────────────
parcel_path = REPO_ROOT / "data/parcels/parcel_01.geojson"
if not parcel_path.exists():
    print("EROARE: Nu exista data/parcels/parcel_01.geojson")
    print("Ruleaza mai intai scripts/check_parcel.py dupa ce creezi fisierul.")
    sys.exit(1)

with open(parcel_path, encoding="utf-8") as file:
    parcel = json.load(file)

geometry = parcel["features"][0]["geometry"]
print(f"Parcela incarcata: {len(geometry['coordinates'][0])} puncte")

# ─── 3. Conectare și autentificare ─────────────────────────────────
print("\nConectare la Copernicus Data Space...")
connection = openeo.connect(
    url="openeo.dataspace.copernicus.eu"
)
connection.authenticate_oidc()
print("Autentificare reusita!")

# ─── 4. Perioadă temporală ─────────────────────────────────────────
# Începem cu o lună de test (iunie 2024).
# După validare, se poate extinde la ["2024-03-01", "2024-11-01"]
TEMPORAL_EXTENT = ["2024-03-01", "2024-11-01"]
print(f"Perioada: {TEMPORAL_EXTENT[0]} - {TEMPORAL_EXTENT[1]}")

# ─── 5. Încărcăm colecția Sentinel-2 L2A ──────────────────────────
# Nu specificăm spatial_extent explicit — openEO îl deduce
# automat din geometria furnizată la aggregate_spatial.
# Documentația oficială confirmă acest comportament.
s2cube = connection.load_collection(
    "SENTINEL2_L2A",
    temporal_extent=TEMPORAL_EXTENT,
    bands=["B04", "B08", "SCL"],
)

# ─── 6. Calculăm NDVI ─────────────────────────────────────────────
red = s2cube.band("B04")
nir = s2cube.band("B08")
ndvi = (nir - red) / (nir + red)

# ─── 7. Construim masca de nori din SCL ───────────────────────────
# SCL clasifică fiecare pixel. Păstrăm doar:
#   4 = vegetation
#   5 = not vegetated (sol vizibil)
# Restul (nori, umbre, apă, etc.) sunt mascate.
scl = s2cube.band("SCL")
mask = ~((scl == 4) | (scl == 5))

# ─── 8. Aplicăm masca pe NDVI ─────────────────────────────────────
ndvi_masked = ndvi.mask(mask)

# ─── 9. Agregare spațială — media NDVI pe parcelă ─────────────────
timeseries = ndvi_masked.aggregate_spatial(
    geometries=parcel,
    reducer="mean",
)

# ─── 10. Lansăm batch job ─────────────────────────────────────────
output_path = output_dir / "parcel_01_2024.csv"
print(f"\nLansare batch job: TerraCycle NDVI June 2024 Parcel 01")
print("Asteptati cateva minute...\n")

job = timeseries.execute_batch(
    out_format="CSV",
   title="TerraCycle NDVI 2024 Parcel 01",
)

# ─── 11. Descărcăm rezultatul ─────────────────────────────────────
job.get_results().download_file(str(output_path))
print(f"\nExport reusit: {output_path}")
print("Ruleaza scripts/inspect_ndvi.py pentru a verifica datele.")
