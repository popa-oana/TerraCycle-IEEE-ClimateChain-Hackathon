r"""
check_parcel.py — Verifică structura GeoJSON a parcelei

Validează faptul că fișierul data/parcels/parcel_01.geojson
este un FeatureCollection valid cu un singur Polygon închis.
Nu verifică dacă parcela e în România sau dacă poligonul
nu se auto-intersectează.

Rulare (din radacina repo-ului):
    .\.venv\Scripts\python.exe scripts\check_parcel.py
"""

import json
from pathlib import Path

# Ancoram caile la radacina repo-ului, ca scriptul sa functioneze
# indiferent de directorul din care este rulat.
REPO_ROOT = Path(__file__).resolve().parents[1]

path = REPO_ROOT / "data/parcels/parcel_01.geojson"

if not path.exists():
    raise FileNotFoundError(
        "Nu exista data/parcels/parcel_01.geojson. "
        "Trebuie sa desenezi o parcela reala in Copernicus Browser "
        "sau geojson.io si sa salvezi fisierul aici."
    )

with open(path, encoding="utf-8") as file:
    data = json.load(file)

if data.get("type") != "FeatureCollection":
    raise ValueError("Fisierul trebuie sa fie FeatureCollection")

if len(data.get("features", [])) != 1:
    raise ValueError(
        "Pentru primul test avem nevoie de o singura parcela"
    )

geometry = data["features"][0]["geometry"]

if geometry.get("type") != "Polygon":
    raise ValueError("Geometria trebuie sa fie Polygon")

ring = geometry["coordinates"][0]

if len(ring) < 4:
    raise ValueError(
        f"Poligonul are doar {len(ring)} puncte, "
        "minim 4 (3 + punctul de inchidere)"
    )

if ring[0] != ring[-1]:
    raise ValueError(
        "Poligonul nu este inchis corect: "
        "primul si ultimul punct trebuie sa fie identice"
    )

# Verificare de baza: coordonatele sunt [lon, lat]
for point in ring:
    if len(point) < 2:
        raise ValueError(f"Punct invalid: {point}")
    lon, lat = point[0], point[1]
    if not (-180 <= lon <= 180):
        raise ValueError(f"Longitudine invalida: {lon}")
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitudine invalida: {lat}")

print("GeoJSON valid!")
print(f"Numar puncte: {len(ring)}")
print(f"Primul punct: {ring[0]}")
print(f"Coordonate [lon, lat] in intervale valide.")
