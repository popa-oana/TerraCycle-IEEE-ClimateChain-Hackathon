r"""
_recover_parcel_04.py — Recovery script for the failed Day 5C parcel_04 job.

The crashed session submitted the coverage-eligible job for parcel_04 but it
failed with a transient server-side error (missing job_specification.json).
The NDVI and coverage-valid jobs completed successfully and their raw files
are preserved in data/ndvi/_staging/.

This script:
1. Re-submits only the missing coverage-eligible job.
2. Downloads the result to the staging directory.
3. Merges all 3 raw files into the standard schema CSV.

It does NOT re-submit the successful jobs and does NOT modify any existing
raw files.
"""
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from backend.ml.quality import (  # noqa: E402
    coverage_means_to_fraction,
    merge_ndvi_and_coverage,
)
from export_ndvi import (  # noqa: E402
    DEFAULT_CONFIG,
    _scl_class_mask,
    build_processing_graphs,
    load_config,
)

STAGING_DIR = REPO_ROOT / "data/ndvi/_staging"
PARCEL_ID = "parcel_04"
CONFIG_PATH = REPO_ROOT / "backend/ml/processing_config_parcel_04.json"
FAILED_JOB_ID = "j-2610191720394a919ddbc320244bc537"
EXPECTED_ELIGIBLE_RAW = STAGING_DIR / f"{PARCEL_ID}_2024_quality_coverage_eligible_raw.csv"
EXPECTED_NDVI_RAW = STAGING_DIR / f"{PARCEL_ID}_2024_quality_ndvi_raw.csv"
EXPECTED_VALID_RAW = STAGING_DIR / f"{PARCEL_ID}_2024_quality_coverage_valid_raw.csv"


def main():
    print("=" * 70)
    print("RECOVERY: Complete parcel_04 coverage-eligible extraction")
    print("=" * 70)

    # Verify existing raw files are present
    for path in [EXPECTED_NDVI_RAW, EXPECTED_VALID_RAW]:
        if not path.exists():
            print(f"ERROR: Expected raw file missing: {path}")
            return 1
        print(f"  Found: {path.name} ({path.stat().st_size} bytes)")

    if EXPECTED_ELIGIBLE_RAW.exists():
        print(f"\nEligible raw already exists: {EXPECTED_ELIGIBLE_RAW.name}")
        print("Skipping job submission, proceeding to merge.")
    else:
        # Load config and parcel
        config = load_config(CONFIG_PATH)
        parcel_path = REPO_ROOT / config["parcel_geojson"]
        with open(parcel_path, encoding="utf-8") as f:
            parcel = json.load(f)

        temporal_extent = [
            config["time_interval"]["start"],
            config["time_interval"]["end"],
        ]

        print(f"\nParcel: {PARCEL_ID}")
        print(f"GeoJSON: {config['parcel_geojson']}")
        print(f"Period: {temporal_extent[0]} .. {temporal_extent[1]}")
        print(f"Previous job {FAILED_JOB_ID} failed (transient server error)")
        print(f"\nConnecting to Copernicus Data Space...")

        import openeo
        connection = openeo.connect(url="openeo.dataspace.copernicus.eu")
        connection.authenticate_oidc()
        print("Authenticated.")

        # Build graphs
        graphs = build_processing_graphs(connection, config, temporal_extent, parcel)
        eligible_cube = graphs["eligible"]

        # Submit the eligible job
        title = f"TerraCycle coverage-eligible {PARCEL_ID} {temporal_extent[0]}"
        print(f"\nSubmitting coverage-eligible job...")
        job = eligible_cube.execute_batch(out_format="CSV", title=title)
        job_id = job.job_id
        print(f"Job submitted: {job_id}")

        # Wait for completion
        print("Waiting for job completion...")
        max_wait = 600  # 10 minutes
        start = time.time()
        while True:
            status = job.status()
            elapsed = time.time() - start
            print(f"  Status: {status} (elapsed: {elapsed:.0f}s)")
            if status == "finished":
                break
            if status == "error":
                print(f"\nERROR: Job {job_id} failed!")
                logs = job.logs()
                for log in logs:
                    print(f"  [{log.get('level', '?')}] {log.get('message', '')}")
                return 1
            if elapsed > max_wait:
                print(f"\nTimeout after {max_wait}s. Job still running: {job_id}")
                return 1
            time.sleep(10)

        # Download result
        print(f"\nDownloading result to {EXPECTED_ELIGIBLE_RAW}...")
        job.get_results().download_file(str(EXPECTED_ELIGIBLE_RAW))
        print(f"Downloaded: {EXPECTED_ELIGIBLE_RAW.name} ({EXPECTED_ELIGIBLE_RAW.stat().st_size} bytes)")

        # Record the new job ID
        print(f"\nNew job ID: {job_id}")

    # Merge all 3 raw files
    print("\n" + "=" * 70)
    print("Merging raw files into standard schema...")
    print("=" * 70)

    ndvi_df = pd.read_csv(EXPECTED_NDVI_RAW)
    valid_df = pd.read_csv(EXPECTED_VALID_RAW)
    eligible_df = pd.read_csv(EXPECTED_ELIGIBLE_RAW)

    print(f"  NDVI rows: {len(ndvi_df)}")
    print(f"  Valid rows: {len(valid_df)}")
    print(f"  Eligible rows: {len(eligible_df)}")

    # Coverage: fraction = valid mean / eligible mean, per date
    coverage_df = coverage_means_to_fraction(valid_df, eligible_df)
    print(f"  Coverage fraction rows: {len(coverage_df)}")

    # Merge into standard schema
    merged = merge_ndvi_and_coverage(ndvi_df, coverage_df, PARCEL_ID)
    print(f"  Merged rows: {len(merged)}")

    # Validate
    missing_fraction = merged["valid_pixel_fraction"].isna().sum()
    if missing_fraction:
        print(f"\n  WARNING: {missing_fraction} observations have no calculable fraction")
    out_of_range = merged["valid_pixel_fraction"].dropna()
    out_of_range = out_of_range[(out_of_range < 0) | (out_of_range > 1)]
    if len(out_of_range):
        print(f"\n  ERROR: {len(out_of_range)} fractions out of [0,1]")
        return 1

    # Write output
    target = REPO_ROOT / "data/ndvi" / f"{PARCEL_ID}_2024_quality.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(target, index=False)
    print(f"\n  Output written: {target}")
    print(f"  Observations: {len(merged)}")
    print(f"  NDVI range: [{merged['ndvi_mean'].min():.6f}, {merged['ndvi_mean'].max():.6f}]")
    print(f"  Fraction range: [{merged['valid_pixel_fraction'].min():.4f}, {merged['valid_pixel_fraction'].max():.4f}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
