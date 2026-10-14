# Satellite Data Quality — Day 4 Implementation

## Purpose

This document describes the Day 4 implementation of data quality, pixel validity, and temporal coverage for TerraCycle Proof satellite-based vegetation verification. The implementation focuses on making evidence quality measurable and transparent.

## 1. What Changed on Day 4

Day 4 implements:

- **Valid pixel fraction** (`valid_pixel_fraction`): Measures what fraction of parcel pixels were actually observable (not cloud-masked) for each acquisition.
- **Temporal coverage**: Measures how well the verification window is covered by valid observations using fixed calendar intervals.
- **Quality filtering**: Excludes observations with `valid_pixel_fraction < 0.50` from valid evidence.
- **Enhanced rules**: Extends `verify_parcel()` to enforce both pixel-quality and temporal-coverage requirements (Rules B and C).
- **Quality module**: New `backend/ml/quality.py` with reusable quality assessment functions.
- **Processing configuration**: New `backend/ml/processing_config.json` documenting all processing parameters.

## 2. Sentinel-2 Data Processing

### Data Source
- **Collection**: `SENTINEL2_L2A` (Surface Reflectance)
- **Bands used**: B04 (Red), B08 (NIR), SCL (Scene Classification Layer)
- **Provider**: Copernicus Data Space (openEO)

### Temporal Range
- **Full season**: `2024-03-01` to `2024-11-01` (exclusive of end) — covers March–October 2024
- **Parcel**: `data/parcels/parcel_01.geojson`

### NDVI Calculation
```text
NDVI = (B08 - B04) / (B08 + B04)
```
NDVI ranges from -1 to +1. Valid NDVI values are constrained to [-1, 1].

## 3. SCL Masking Policy

The Scene Classification Layer classifies each pixel. For agricultural NDVI analysis, we retain only classes that represent vegetation or visible bare soil.

**Accepted SCL classes:**
- **Class 4**: Vegetation
- **Class 5**: Not vegetated (bare soil visible)

**Excluded SCL classes:** All others (0: No data, 1: Saturated/defective, 2: Dark area, 3: Cloud shadows, 6: Water, 7: Unclassified, 8: Medium-prob clouds, 9: High-prob clouds, 10: Thin cirrus, 11: Snow/ice).

This is a conservative policy. It removes clouds, cloud shadows, water bodies, defective pixels, and unclassified pixels. It does **not** guarantee complete absence of clouds at subpixel level or thin haze. 

## 4. Valid Pixel Fraction Calculation

**Definition:** 
```text
valid_pixel_fraction = number of valid pixels / number of eligible pixels inside the parcel
```

Where:
- **Valid pixels** = pixels inside the parcel that satisfy the SCL acceptance criteria (classes 4 or 5) and are not masked by quality flags.
- **Eligible pixels** = total pixels inside the parcel boundary for that acquisition (denominator computed before applying cloud/quality exclusions).

**Key requirements:**
- Computed separately for each satellite observation.
- Uses the same spatial parcel boundary as NDVI aggregation.
- Denominator excludes pixels outside the parcel.
- Handles no-data and zero-denominator cases safely.
- NDVI mean and quality metrics correspond to the same acquisition.

**How it is computed in this project:** `scripts/export_ndvi.py` builds a parallel
openEO graph from the *same* accepted-pixel mask used for the NDVI:
```text
valid_flags   = ((SCL == 4) | (SCL == 5)).astype("float32")   # 1 = valid, 0 = masked
valid_fraction = valid_flags.aggregate_spatial(geometry, reducer="mean")
```
The mean of a 0/1 band over the parcel equals `valid pixels / all parcel pixels`,
i.e. the denominator is the whole parcel computed *before* cloud exclusion, exactly
as required. Cloudy, shadowed, water, defective and no-data pixels all count as
invalid (0). The NDVI mean uses the same mask but masks those pixels out so that
only valid pixels contribute. The two aggregated CSV exports are merged by
acquisition timestamp into the standard schema via
`backend.ml.quality.merge_ndvi_and_coverage`.

Because this requires a live openEO batch job, the existing real CSVs in
`data/ndvi/` still have no `valid_pixel_fraction` column; `verify_parcel()` accepts
CSVs both with and without it and reports `evidence_quality: "unknown"` when it is
absent. The merge logic is covered by offline tests with mocked openEO outputs.

## 5. Temporal Coverage Calculation

**Definition:**
```text
temporal_coverage = intervals_with_valid_observations / total_intervals
```

**Policy:**
- **Interval length:** 10 days (configurable; see `processing_config.json`)
- **Counting:** An interval is "covered" if it contains ≥ 1 valid observation
- **Window**: Determined by verification policy (`window_start`, `window_end`)
- **Handling:** Partial intervals at start/end are counted toward total intervals; multiple observations in the same interval count as 1 covered interval.

**Example:** For a 90-day window with 10-day intervals, total_intervals = 9. If valid observations occur in 5 intervals, temporal_coverage = 5/9 ≈ 0.555.

Temporal coverage is independent of pixel coverage — both must be satisfied.

## 6. Quality Rules

The following rules are enforced in `verify_parcel()` when quality metadata is present:

- **Rule A (Minimum observations):** Fewer than `min_observations` (default 5) valid observations → `inconclusive` (`reason_code: INSUFFICIENT_OBSERVATIONS`). (Legacy rule, preserved.)
- **Rule B (Minimum temporal coverage):** Only enforced when the policy provides both `window_start` and `window_end`. If `temporal_coverage < min_temporal_coverage` (default 0.5) the verdict becomes `inconclusive` (`reason_code: INSUFFICIENT_TEMPORAL_COVERAGE`). When no window is provided, the rule is not applied and a warning is reported.
- **Rule C (Pixel quality):** Only enforced when the CSV contains a `valid_pixel_fraction` column. Observations with `valid_pixel_fraction < min_valid_pixel_fraction` (default 0.50) are removed from valid evidence; a missing value is treated as *unknown* (not passing). When the column is absent entirely, the rule is not applied and `evidence_quality` is reported as `"unknown"` with a warning.

These rules distinguish between:
- **Evidence quality** (pixel coverage, temporal coverage, observation count)
- **Experimental vegetation classification** (NDVI thresholding against valid observations)
- **Agronomic compliance** (out of scope for this prototype)

## 7. When Results are Inconclusive

`verify_parcel()` returns `inconclusive` (verdict_code 2) when:
1. No NDVI CSV found for parcel → `reason_code: "MISSING_EVIDENCE"`
2. CSV cannot be read → `reason_code: "CSV_READ_ERROR"`
3. Missing required columns (date, ndvi_mean) → `reason_code: "INVALID_CSV_STRUCTURE"`
4. Insufficient valid observations after filtering → `reason_code: "INSUFFICIENT_OBSERVATIONS"`
5. Insufficient temporal coverage (if policy specifies `min_temporal_coverage` and data allows computation) → `reason_code: "INSUFFICIENT_TEMPORAL_COVERAGE"` or `INSUFFICIENT_OBSERVATIONS` as appropriate

Importantly: **NDVI alone does not imply compliance**. Vegetation presence is necessary but not sufficient to demonstrate sustainable practices.

## 8. Reproducing the Pipeline

### Prerequisites
- Python 3.11+ (venv activated)
- Dependencies: `pip install -r requirements-ml.txt` (includes openeo, pandas, numpy, pytest)

All commands run from the repository root.

### Validate parcel geometry
```powershell
.\.venv\Scripts\python.exe scripts/check_parcel.py
```

### Inspect existing NDVI data
```powershell
.\.venv\Scripts\python.exe scripts/inspect_ndvi.py
```

### Run provisional verification (uses existing real CSVs)
```powershell
.\.venv\Scripts\python.exe scripts/run_real_verification.py
```

### Run tests
```powershell
# Manual test scenarios (Day 3)
.\.venv\Scripts\python.exe tests/test_rules.py

# Comprehensive rules suite (Day 3)
.\.venv\Scripts\python.exe -m pytest tests/test_rules_pytest.py -v

# Day 4 quality / coverage / export-merge suite
.\.venv\Scripts\python.exe -m pytest tests/test_quality.py -v

# Everything
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

### Export full-season NDVI + valid pixel fraction (requires Copernicus auth)
```powershell
.\.venv\Scripts\python.exe scripts\export_ndvi.py            # writes to _quality.csv if target exists
.\.venv\Scripts\python.exe scripts\export_ndvi.py --force    # overwrite the target CSV
.\.venv\Scripts\python.exe scripts\export_ndvi.py --dry-run  # build the graph only
```

**Note:** `export_ndvi.py` requires browser-based OIDC authentication to Copernicus Data Space. If auth is not available, inspect existing CSVs (`data/ndvi/parcel_01_2024.csv`, `parcel_01_june_2024.csv`) instead.

## 9. Configuration & Reproducibility

All processing parameters are stored in `backend/ml/processing_config.json`. Key fields:
- `time_interval`: start/end for full season (also used as the verification window)
- `parcel_geojson`: parcel boundary used for aggregation
- `output_csv`: target path for the merged export
- `scl_accepted_classes`: [4,5] with rationale
- `min_valid_pixel_fraction`: 0.5
- `temporal_coverage.interval_length_days`: 10
- `temporal_coverage.min_temporal_coverage`: 0.5
- `min_valid_observations`: 5
- `processing_version`: day4-v1.0.0

**Reproducibility guarantees:**
- Raw data files are never overwritten silently (existing files preserved).
- Chronological sorting applied deterministically.
- Duplicate timestamps deduplicated (keep first).
- Identical inputs + configuration produce identical outputs.
- CSV schema is consistent; `valid_pixel_fraction` is optional but preserved when present.

## 10. Current Limitations

1. **Pixel fraction in existing real CSVs**: The export pipeline (`scripts/export_ndvi.py`) now computes `valid_pixel_fraction` (mean of the accepted-pixel mask) and merges it with the NDVI series. However, the real CSVs currently committed in `data/ndvi/` were produced before this change and therefore lack the column; they cannot be retro-fitted offline because pixel counts are not stored. `verify_parcel()` accepts CSVs both with and without this column and flags missing quality metadata as `evidence_quality: "unknown"`.
2. **Temporal coverage computation**: Requires `window_start`/`window_end` in policy and acquisition dates. When policy omits these, temporal coverage is not enforced (legacy behavior preserved for backward compatibility).
3. **Live full-season export**: `scripts/export_ndvi.py` was updated and dry-run/CLI-verified, but the live batch job requires browser-based Copernicus OIDC authentication and was **not executed** in this session. Live values for `valid_pixel_fraction` are therefore **pending**; existing real CSVs (`parcel_01_2024.csv`) are used for verification. The merge logic is tested offline with mocked openEO outputs.
4. **Scene IDs**: The aggregated openEO output may not expose individual scene IDs in the CSV. The schema accepts `scene_id` optionally; when missing, it's not fabricated.
5. **Agronomic validity**: NDVI cannot demonstrate absence of herbicides, compliance with fertilization rules, or organic certification.

## 11. Corina Integration Notes

Corina's backend should consume:
- **Primary interface:** `verify_parcel(parcel_id, policy, evidence_directory)` from `backend.ml.rules`
- **Extended quality utilities:** `backend.ml.quality` for pixel filtering, temporal coverage calculation, NDVI/SCL primitives, and export merging
- **Processing config:** `backend/ml/processing_config.json` for policy defaults/metadata
- **Evidence format:** See `backend/ml/README.md` for the full return schema. The `quality` block now always includes `evidence_quality`, `quality_excluded_count`, `temporal_coverage`, `covered_intervals`, `total_intervals`, `interval_length_days` and `warnings` (in addition to `valid_count`/`total_rows`/`excluded_count`). When `valid_pixel_fraction` is present in the CSV, each observation also includes it.

**Key integration points:**
- Verdict codes remain 0/1/2 (unchanged). 
- Function never raises exceptions; all error states return `inconclusive` with `reason_code`.
- CSV paths are resolved relative to `evidence_directory`; function prefers `_2024.csv`, then `_june_2024.csv`, then `_clean.csv`.
- Observations are sorted chronologically and deduplicated by date.

## 12. Reserved for Day 5/Day 6

- Train/test split by `parcel_id` (GroupKFold) with independent test set.
- Feature engineering (temporal features, slope, min/max, interval coverage) without leakage.
- LightGBM baseline + evaluation with confusion matrix/F1.
- Evidence document canonicalization/hashing (separately owned by Corina; schema alignment).
- Labels from `data/labels.csv` integration.
- Feeding live `valid_pixel_fraction` values from a real export into the committed CSVs.