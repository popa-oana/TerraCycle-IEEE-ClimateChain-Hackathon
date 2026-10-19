r"""
export_ndvi.py — Extrage seria temporală NDVI + fracția reală de pixeli valizi

Fluxul (Day 4 + Task 3A acoperire pixeli):
  1. Citește configurația din backend/ml/processing_config.json
  2. Citește parcela din GeoJSON (cale din configurație)
  3. Se conectează la Copernicus Data Space (openEO) — fără autentificare
     pentru construirea grafului (--dry-run nu cere autentificare)
  4. Încarcă colecția SENTINEL2_L2A cu benzile B04, B08, SCL
  5. Calculează NDVI = (B08 - B04) / (B08 + B04)
  6. Construiește masca de calitate din SCL (păstrează doar clasele 4 și 5)
  7. Aplică masca pe NDVI (media se face doar pe pixeli valizi), după ce
     masca este reșapată explicit pe grila NDVI de 10 m (nearest neighbour)
  8. Calculează acoperirea ca raport a două agregări pe parcelă, AMBELE
     derivate numai din SCL (grila nativă de 20 m):
        valid_pixel_fraction = mean(valid_flags)   / mean(eligible_flags)
        valid_flags    = 1 pentru SCL in {4, 5}          (pixeli valizi)
        eligible_flags = 1 pentru SCL in {1..11}         (observații reale)
     Numitorul (pixelii eligibili) este astfel determinat ÎNAINTE de
     mascarea calitativă: norii/umbrele rămân eligibili (numărate ca
     nevalide), iar pixelii fără date (SCL 0 / lipsă) sunt excluși total.
     Raportul se calculează pe client, cu gardă pentru numitor zero și
     valori lipsă; rezultatul este mereu în [0, 1] sau null.
  9. Descarcă CSV-urile brute în data/ndvi/_staging/ (fișierele sunt
     denumite după output-ul configurației, astfel încât diferite
     configurații nu se suprascriu între ele) și le combină în schema
     standard: parcel_id, acquired_at, scene_id, ndvi_mean,
     valid_pixel_fraction
 10. Scrie rezultatul ÎN SIGURANȚĂ (nu suprascrie date reale fără --force)

Rulare (din radacina repo-ului):
    .\.venv\Scripts\python.exe scripts\export_ndvi.py
    .\.venv\Scripts\python.exe scripts\export_ndvi.py --force
    .\.venv\Scripts\python.exe scripts\export_ndvi.py --dry-run
    .\.venv\Scripts\python.exe scripts\export_ndvi.py --reuse-ndvi data/ndvi/parcel_01_2024.csv

--reuse-ndvi <csv> reutilizează un export NDVI existent (configurație de
procesare compatibilă, verificabilă prin valorile comune) și rulează DOAR
cele două joburi de acoperire (valid/eligible), fără a rula din nou jobul
NDVI și fără a suprascrie descărcările brute existente.

--dry-run construiește graful, îl serializează în
data/ndvi/_staging/graphs/, verifică procesele folosite față de lista de
procese suportate de backend și (dacă backendul permite fără autentificare)
apelează validarea server-side. NU pornește niciun batch job și NU cere
autentificare.

Necesită autentificare OIDC (browser) doar pentru execuția reală.
Joburile pot dura câteva minute fiecare.
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
    ELIGIBLE_SCL_CLASSES,
    coverage_means_to_fraction,
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
        "scl_eligible_classes",
    }
    missing = required - set(config)
    if missing:
        print(f"EROARE: Configurația nu conține câmpurile: {sorted(missing)}")
        sys.exit(1)
    return config


def _scl_class_mask(scl, classes) -> object:
    """Binary mask (openEO cube): 1 where SCL equals one of `classes`."""
    mask = None
    for cls in classes:
        current = scl == cls
        mask = current if mask is None else (mask | current)
    return mask


def build_processing_graphs(connection, config, temporal_extent, parcel) -> dict:
    """
    Build the three openEO processing graphs.

    Returns {"ndvi": DataCube, "valid": DataCube, "eligible": DataCube}.

    Policies implemented here (documented in processing_config.json and
    docs/satellite-quality.md):

    * NDVI graph: NDVI from B04/B08 (10 m native), masked with the
      SCL quality mask. The categorical mask is explicitly resampled onto
      the 10 m NDVI grid with nearest neighbour (`resample_cube_spatial`,
      method="near") so 10 m and 20 m pixels are never silently combined.
    * Coverage numerator and denominator: BOTH flag bands are derived from
      the SCL band alone (20 m native) and aggregated with the same
      `aggregate_spatial` call over the same parcel FeatureCollection, so
      numerator and denominator share an identical spatial grid and
      geometry. The fraction itself is computed client-side.

    Building the graphs requires no authentication; running them does.
    """
    s2cube = connection.load_collection(
        config["collection"],
        temporal_extent=temporal_extent,
        bands=config["bands"],
    )
    red = s2cube.band("B04")
    nir = s2cube.band("B08")
    ndvi = (nir - red) / (nir + red)

    scl = s2cube.band("SCL")

    # Valid pixels: SCL vegetation (4) / not vegetated (5).
    valid_mask = _scl_class_mask(scl, ACCEPTED_SCL_CLASSES)
    # Eligible pixels (denominator, BEFORE cloud masking): observed classes
    # 1..11; SCL 0 (NO DATA) and missing pixels carry no observation.
    eligible_classes = tuple(config.get("scl_eligible_classes") or ELIGIBLE_SCL_CLASSES)
    eligible_mask = _scl_class_mask(scl, eligible_classes)

    invalid_mask = ~valid_mask
    # 10 m / 20 m policy: nearest-neighbour resampling of the SCL-derived
    # mask onto the B04/B08 (10 m) grid before applying it to NDVI.
    invalid_mask_10m = invalid_mask.resample_cube_spatial(target=red, method="near")

    # NDVI mean over valid pixels only.
    ndvi_ts = ndvi.mask(invalid_mask_10m).aggregate_spatial(
        geometries=parcel, reducer="mean"
    )

    # Coverage: numerator and denominator, both from SCL (same 20 m grid),
    # spatially aggregated over the same parcel polygon per date.
    valid_ts = valid_mask.convert_data_type("float32").aggregate_spatial(
        geometries=parcel, reducer="mean"
    )
    eligible_ts = eligible_mask.convert_data_type("float32").aggregate_spatial(
        geometries=parcel, reducer="mean"
    )

    return {"ndvi": ndvi_ts, "valid": valid_ts, "eligible": eligible_ts}


def _iter_process_ids(graph: dict):
    """Yield every process_id in a (possibly nested) process graph dict."""
    if isinstance(graph, dict):
        if "process_id" in graph and isinstance(graph.get("process_id"), str):
            yield graph["process_id"]
        for value in graph.values():
            yield from _iter_process_ids(value)
    elif isinstance(graph, list):
        for item in graph:
            yield from _iter_process_ids(item)


def graph_summary(cube) -> dict:
    """Serializable summary of a processing graph (node count + processes)."""
    graph = json.loads(cube.to_json())["process_graph"]
    return {
        "nodes": len(graph),
        "processes": sorted(set(_iter_process_ids(graph))),
    }


def check_graphs_against_backend(connection, graphs: dict) -> list:
    """Compare every process used by the graphs against the backend's
    published process list (read-only, no authentication, no job).

    Returns a list of problem strings; empty list means all processes are
    advertised by the backend. Network failures are reported, not raised.
    """
    try:
        backend_processes = {
            p.get("id") for p in connection.list_processes() if p.get("id")
        }
    except Exception as exc:  # pragma: no cover - depends on network
        return [f"could not fetch backend process list: {exc}"]
    problems = []
    for name, cube in graphs.items():
        for process_id in graph_summary(cube)["processes"]:
            if process_id not in backend_processes:
                problems.append(f"graph '{name}' uses unsupported process '{process_id}'")
    return problems


def serialize_graphs(graphs: dict, parcel_id: str) -> Path:
    """Write each processing graph to data/ndvi/_staging/graphs/ for review."""
    out_dir = REPO_ROOT / "data/ndvi/_staging/graphs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, cube in graphs.items():
        path = out_dir / f"{parcel_id}_{name}_graph.json"
        path.write_text(cube.to_json(), encoding="utf-8")
    return out_dir


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
        help="Build, serialize and statically check the processing graphs "
        "without authenticating and without running a batch job",
    )
    parser.add_argument(
        "--reuse-ndvi",
        default=None,
        metavar="CSV",
        help="Reuse an existing NDVI export (raw or standard schema) instead "
        "of running the NDVI batch job; only the two coverage jobs run. "
        "Use only when the export's processing configuration is compatible.",
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
    print("TERRACYCLE — EXPORT NDVI (Day 4, cu fracție reală de pixeli valizi)")
    print("=" * 70)
    print(f"Parcela:        {parcel_id}")
    print(f"GeoJSON:        {config['parcel_geojson']}")
    print(f"Perioada:       {temporal_extent[0]} .. {temporal_extent[1]}")
    print(f"Colecția:       {config['collection']}")
    print(f"Benzi:          {bands}")
    print(f"Clase SCL OK:   {config['scl_accepted_classes']} (pixeli valizi)")
    print(f"Clase eligibile:{config['scl_eligible_classes']} (numitor, înainte de mascare)")
    print(f"Config:         {args.config}")

    if not parcel_path.exists():
        print(f"\nEROARE: Nu exista {config['parcel_geojson']}")
        print("Ruleaza mai intai scripts/check_parcel.py")
        return 1

    with open(parcel_path, encoding="utf-8") as file:
        parcel = json.load(file)
    geometry = parcel["features"][0]["geometry"]
    print(f"Parcela incarcata: {len(geometry['coordinates'][0])} puncte")

    # --- Connection (no authentication yet: graph building is local) ---
    import openeo  # imported here so --help works without the dependency

    print("\nConectare la Copernicus Data Space (fără autentificare)...")
    connection = openeo.connect(url="openeo.dataspace.copernicus.eu")

    # --- Build the processing graphs ---
    graphs = build_processing_graphs(connection, config, temporal_extent, parcel)

    if args.dry_run:
        print("\n--dry-run: graful a fost construit, nu se lansează joburi și "
              "nu se cere autentificarea.")
        for name, cube in graphs.items():
            summary = graph_summary(cube)
            print(f"  {name:9s}: {summary['nodes']} noduri; procese: "
                  f"{', '.join(summary['processes'])}")
        out_dir = serialize_graphs(graphs, parcel_id)
        print(f"  Grafuri serializate în: {out_dir}")
        problems = check_graphs_against_backend(connection, graphs)
        if problems:
            print("  Probleme găsite la verificarea față de backend:")
            for problem in problems:
                print(f"    - {problem}")
            return 1
        print("  Toate procesele sunt advertised de backendul Copernicus.")
        for name, cube in graphs.items():
            try:
                response = cube.validate()
                print(f"  Validare server-side '{name}': {response}")
            except Exception as exc:
                print(f"  Validare server-side '{name}': indisponibilă fără "
                      f"autentificare ({type(exc).__name__}: {exc})")
        print("  NOTĂ: validarea statică NU garantează că execuția server-side "
              "va reuși; acest lucru se confirmă doar printr-un job real.")
        return 0

    # --- Authentication (browser) only for the real run ---
    print("\nAutentificare OIDC (necesită browser)...")
    connection.authenticate_oidc()
    print("Autentificare reusita!")

    staging_dir = REPO_ROOT / "data/ndvi/_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    target = REPO_ROOT / config.get(
        "output_csv", f"data/ndvi/{parcel_id}_2024.csv"
    )
    # Staging files are keyed by the output name, so different configs
    # (full season vs June test window, etc.) never overwrite each other's
    # raw downloads.
    output_stem = target.stem
    jobs = {
        "ndvi": (staging_dir / f"{output_stem}_ndvi_raw.csv",
                 f"TerraCycle NDVI {parcel_id} {temporal_extent[0]}"),
        "valid": (staging_dir / f"{output_stem}_coverage_valid_raw.csv",
                  f"TerraCycle coverage-valid {parcel_id} {temporal_extent[0]}"),
        "eligible": (staging_dir / f"{output_stem}_coverage_eligible_raw.csv",
                     f"TerraCycle coverage-eligible {parcel_id} {temporal_extent[0]}"),
    }

    if args.reuse_ndvi:
        ndvi_source = REPO_ROOT / args.reuse_ndvi
        if not ndvi_source.exists():
            print(f"\nEROARE: --reuse-ndvi: nu exista {ndvi_source}")
            return 1
        print(f"\nReutilizez exportul NDVI existent (fără job NDVI): "
              f"{ndvi_source}")
    else:
        target_ndvi, title_ndvi = jobs["ndvi"]
        print(f"\nLansare batch job 'ndvi' (poate dura cateva minute)...")
        job = graphs["ndvi"].execute_batch(out_format="CSV", title=title_ndvi)
        job.get_results().download_file(str(target_ndvi))
        ndvi_source = target_ndvi

    for name in ("valid", "eligible"):
        target_job, title_job = jobs[name]
        print(f"\nLansare batch job '{name}' (poate dura cateva minute)...")
        job = graphs[name].execute_batch(out_format="CSV", title=title_job)
        job.get_results().download_file(str(target_job))

    # --- Coverage: fraction = valid mean / eligible mean, per date ---
    valid_df = pd.read_csv(jobs["valid"][0])
    eligible_df = pd.read_csv(jobs["eligible"][0])
    coverage_df = coverage_means_to_fraction(valid_df, eligible_df)

    # --- Merge into the standard schema, aligned on acquisition date ---
    ndvi_df = pd.read_csv(ndvi_source)
    merged = merge_ndvi_and_coverage(ndvi_df, coverage_df, parcel_id)

    missing_fraction = merged["valid_pixel_fraction"].isna().sum()
    if missing_fraction:
        print(f"\nATENȚIE: {missing_fraction} observații nu au fracție calculabilă "
              "(pixeli eligibili zero sau SCL lipsă) și rămân null, nu inventate.")
    out_of_range = merged["valid_pixel_fraction"].dropna()
    out_of_range = out_of_range[(out_of_range < 0) | (out_of_range > 1)]
    if len(out_of_range):
        print(f"\nEROARE: {len(out_of_range)} fracții în afara intervalului [0,1]")
        return 1

    # --- Non-destructive output (target resolved above from the config) ---
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
    print(f"CSV-uri brute păstrate în: {staging_dir}")
    print("Ruleaza scripts/inspect_ndvi.py pentru a verifica datele.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
