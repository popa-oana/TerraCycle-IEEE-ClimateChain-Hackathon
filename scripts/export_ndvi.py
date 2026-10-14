r"""
export_ndvi.py — Extrage seria temporală NDVI din Sentinel-2 via openEO

Fluxul (Day 4):
  1. Citește configurația din backend/ml/processing_config.json
  2. Citește parcela din GeoJSON (cale din configurație)
  3. Se autentifică la Copernicus Data Space (openEO)
  4. Încarcă colecția SENTINEL2_L2A cu benzile B04, B08, SCL
  5. Calculează NDVI = (B08 - B04) / (B08 + B04)
  6. Construiește masca de calitate din SCL (păstrează doar clasele 4 și 5)
  7. Aplică masca pe NDVI (media se face doar pe pixeli valizi)
  8. Calculează separat fracția de pixeli valizi pe parcelă
     (media unei benzi 0/1: 1 = pixel valid, 0 = pixel mascat)
  9. Descarcă două CSV-uri temporare și le unește în schema standard:
     parcel_id, acquired_at, scene_id, ndvi_mean, valid_pixel_fraction
 10. Scrie rezultatul ÎN SIGURANȚĂ (nu suprascrie date reale fără --force)

Rulare (din radacina repo-ului):
    .\.venv\Scripts\python.exe scripts\export_ndvi.py
    .\.venv\Scripts\python.exe scripts\export_ndvi.py --force
    .\.venv\Scripts\python.exe scripts\export_ndvi.py --dry-run

Necesită autentificare OIDC (browser). Jobul poate dura câteva minute.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Console Windows poate folosi cp1252; fortam UTF-8 ca sa nu crape la diacritice.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ancoram caile la radacina repo-ului.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ml.quality import (  # noqa: E402
    ACCEPTED_SCL_CLASSES,
    merge_ndvi_and_coverage,
)

DEFAULT_CONFIG = REPO_ROOT / "backend/ml/processing_config.json"


def load_config(config_path: Path) -> dict:
    """Load and validate the processing configuration."""
    if not config_path.exists():
        print(f"EROARE: Nu exista configurația {config_path}")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    required = {
        "parcel_id",
        "parcel_geojson",
        "time_interval",
        "collection",
        "bands",
        "scl_accepted_classes",
    }
    missing = required - set(config)
    if missing:
        print(f"EROARE: Configurația nu conține câmpurile: {sorted(missing)}")
        sys.exit(1)
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Sentinel-2 NDVI export (Day 4)")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to processing_config.json",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target output CSV if it already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the processing graph without running a batch job",
    )
    args = parser.parse_args()

    config = load_config(Path(args.config))
    parcel_id = config["parcel_id"]
    parcel_path = REPO_ROOT / config["parcel_geojson"]
    temporal_extent = [
        config["time_interval"]["start"],
        config["time_interval"]["end"],
    ]
    bands = config["bands"]

    print("=" * 70)
    print("TERRACYCLE — EXPORT NDVI (Day 4, cu fracție de pixeli valizi)")
    print("=" * 70)
    print(f"Parcela:        {parcel_id}")
    print(f"GeoJSON:        {config['parcel_geojson']}")
    print(f"Perioada:       {temporal_extent[0]} .. {temporal_extent[1]}")
    print(f"Colecția:       {config['collection']}")
    print(f"Benzi:          {bands}")
    print(f"Clase SCL OK:   {config['scl_accepted_classes']}")
    print(f"Config:         {args.config}")

    if not parcel_path.exists():
        print(f"\nEROARE: Nu exista {config['parcel_geojson']}")
        print("Ruleaza mai intai scripts/check_parcel.py")
        return 1

    with open(parcel_path, encoding="utf-8") as file:
        parcel = json.load(file)
    geometry = parcel["features"][0]["geometry"]
    print(f"Parcela incarcata: {len(geometry['coordinates'][0])} puncte")

    # --- Authentication (requires browser) ---
    import openeo  # imported here so --help works without the dependency

    print("\nConectare la Copernicus Data Space...")
    connection = openeo.connect(url="openeo.dataspace.copernicus.eu")
    connection.authenticate_oidc()
    print("Autentificare reusita!")

    # --- Build the processing graph ---
    s2cube = connection.load_collection(
        config["collection"],
        temporal_extent=temporal_extent,
        bands=bands,
    )
    red = s2cube.band("B04")
    nir = s2cube.band("B08")
    ndvi = (nir - red) / (nir + red)

    scl = s2cube.band("SCL")
    accepted = None
    for cls in ACCEPTED_SCL_CLASSES:
        accepted = (scl == cls) if accepted is None else (accepted | (scl == cls))
    invalid_mask = ~accepted

    # NDVI mean over valid pixels only.
    ndvi_masked = ndvi.mask(invalid_mask)
    ndvi_ts = ndvi_masked.aggregate_spatial(geometries=parcel, reducer="mean")

    # Valid pixel fraction = mean of a 0/1 mask over ALL parcel pixels.
    # Denominator is the parcel itself; masked/cloudy pixels count as invalid.
    valid_flags = accepted.astype("float32")
    coverage_ts = valid_flags.aggregate_spatial(geometries=parcel, reducer="mean")

    if args.dry_run:
        print("\n--dry-run: graful a fost construit, nu se lansează joburi.")
        print(f"  NDVI graph nodes: {len(ndvi_ts.graph['process_graph'])}")
        print(f"  Coverage graph nodes: {len(coverage_ts.graph['process_graph'])}")
        return 0

    staging_dir = REPO_ROOT / "data/ndvi/_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    ndvi_stage = staging_dir / f"{parcel_id}_ndvi_raw.csv"
    coverage_stage = staging_dir / f"{parcel_id}_coverage_raw.csv"

    print("\nLansare batch job NDVI (poate dura cateva minute)...")
    ndvi_job = ndvi_ts.execute_batch(
        out_format="CSV", title=f"TerraCycle NDVI {parcel_id} {temporal_extent[0]}"
    )
    ndvi_job.get_results().download_file(str(ndvi_stage))

    print("Lansare batch job fracție pixeli valizi...")
    coverage_job = coverage_ts.execute_batch(
        out_format="CSV",
        title=f"TerraCycle valid-coverage {parcel_id} {temporal_extent[0]}",
    )
    coverage_job.get_results().download_file(str(coverage_stage))

    # --- Merge into the standard schema ---
    ndvi_df = pd.read_csv(ndvi_stage)
    coverage_df = pd.read_csv(coverage_stage)
    merged = merge_ndvi_and_coverage(ndvi_df, coverage_df, parcel_id)

    # --- Non-destructive output ---
    target = REPO_ROOT / config.get(
        "output_csv", f"data/ndvi/{parcel_id}_2024.csv"
    )
    if target.exists() and not args.force:
        print(
            f"\nATENȚIE: {target} există deja. Nu îl suprascriu fără --force.\n"
            f"  Scriu în schimb: {target.with_name(target.stem + '_quality' + target.suffix)}\n"
            f"  Rulează din nou cu --force pentru a înlocui fișierul original."
        )
        target = target.with_name(target.stem + "_quality" + target.suffix)

    target.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(target, index=False)
    print(f"\nExport reușit: {target} ({len(merged)} observații)")
    print("Ruleaza scripts/inspect_ndvi.py pentru a verifica datele.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
