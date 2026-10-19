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
- **Valid pixels** = pixels inside the parcel that satisfy the SCL acceptance criteria (classes 4 or 5).
- **Eligible pixels** = pixels inside the parcel for that acquisition that carry an actual SCL observation (classes 1–11), i.e. the denominator is determined **before** cloud-quality masking. Cloudy, shadowed and defective pixels stay in the denominator and count as *not valid*. SCL class 0 (`NO DATA`) and missing/NaN pixels carry no observation at all and are excluded from the denominator entirely — not every pixel is assumed to have a valid observation.

**Key requirements:**
- Computed separately for each satellite observation.
- Uses the same spatial parcel boundary as NDVI aggregation.
- Denominator excludes pixels outside the parcel.
- Handles no-data and zero-denominator cases safely.
- NDVI mean and quality metrics correspond to the same acquisition.

**How it is computed in this project:** `scripts/export_ndvi.py` builds three
openEO graphs from the same `SENTINEL2_L2A` load. Two of them cover pixel
quality — both derived from the **SCL band alone** (20 m native resolution),
so numerator and denominator share an identical spatial grid — and both
aggregate with the same `aggregate_spatial` call over the same parcel
FeatureCollection:

```text
valid_flags     = ((SCL == 4) | (SCL == 5)).convert_data_type("float32")
eligible_flags  = ((SCL >= 1) | ... | (SCL == 11)).convert_data_type("float32")
valid_mean      = valid_flags.aggregate_spatial(parcel, reducer="mean")
eligible_mean   = eligible_flags.aggregate_spatial(parcel, reducer="mean")

# computed client-side, per acquisition date:
valid_pixel_fraction = valid_mean / eligible_mean
```

Because both means are taken over the same pixels on the same grid, the
ratio of the means equals `valid pixels / eligible pixels`. The division is
done **client-side** (`backend/ml/quality.py::compute_valid_pixel_fraction`)
so that a zero/missing denominator yields `null` — never a fabricated value —
and every produced fraction is clipped to `[0, 1]`. Cloudy, shadowed and
defective pixels are eligible (denominator) but invalid (numerator); no-data
and missing SCL pixels are excluded from both. The NDVI mean uses the same
valid-pixel mask so that only valid pixels contribute to `ndvi_mean`. The
three raw CSV exports are combined via `coverage_means_to_fraction` and
merged by acquisition timestamp into the standard schema via
`backend/ml.quality.merge_ndvi_and_coverage`.

**Resolution policy (10 m / 20 m):** B04/B08 are 10 m native, SCL is 20 m
native. The coverage numerator and denominator are computed exclusively on
the 20 m SCL grid, so no arithmetic ever mixes resolutions inside the
fraction. For the NDVI graph, the SCL-derived categorical mask is explicitly
resampled onto the 10 m NDVI grid with nearest neighbour
(`resample_cube_spatial`, `method="near"`) before `mask` is applied —
nearest neighbour is the correct resampling for class labels. This policy is
recorded in `processing_config.json` under `coverage_policy`.

Because this requires a live openEO batch job, the pipeline was executed for
real (2026-10-19): `data/ndvi/parcel_01_june_2024_quality.csv` (June test
window) and `data/ndvi/parcel_01_2024_quality.csv` (full season) now contain
genuine `valid_pixel_fraction` values per acquisition (see §9).
`verify_parcel()` prefers these `_quality` exports when present, so Rule C is
enforced on real measurements; CSVs without the column remain supported with
`evidence_quality: "unknown"`. The merge logic is covered by offline tests
with mocked openEO outputs (`tests/test_pixel_coverage.py`).

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
- **Rule B (Minimum temporal coverage):** Enforced only when the policy provides both `window_start` and `window_end` and they form a valid UTC window (inclusive start / exclusive end). If `temporal_coverage < min_temporal_coverage` (default 0.5) the verdict becomes `inconclusive` (`reason_code: INSUFFICIENT_TEMPORAL_COVERAGE`). When no window is provided, the rule is not applied and warnings mark the legacy mode as experimental / not settlement-ready. If a window is explicitly supplied but invalid (missing one boundary, unparseable date, or `window_end <= window_start`), `verify_parcel()` returns `inconclusive` with `reason_code: "INVALID_INPUT"` and never falls back to the whole dataset.
- **Rule C (Pixel quality):** Only enforced when the CSV contains a `valid_pixel_fraction` column. Observations with `valid_pixel_fraction < min_valid_pixel_fraction` (default 0.50) are removed from valid evidence; a missing value is treated as *unknown* (not passing). When the column is absent entirely, the rule is not applied and `evidence_quality` is reported as `"unknown"` with a warning that the result is experimental and must not be treated as settlement-ready verification.

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
5. Insufficient temporal coverage (if policy specifies a valid window and `min_temporal_coverage`) → `reason_code: "INSUFFICIENT_TEMPORAL_COVERAGE"`
6. Invalid commitment window (explicitly supplied but missing boundary, unparseable date, or `window_end <= window_start`) → `reason_code: "INVALID_INPUT"` (fails safely; never evaluates entire dataset)

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

# Task 3A pixel-coverage + processing-graph suite
.\.venv\Scripts\python.exe -m pytest tests/test_pixel_coverage.py -v

# Day 5A/5B dataset + feature-engineering suites
.\.venv\Scripts\python.exe -m pytest tests/test_prepare_ml_dataset.py tests/test_features.py -q

# Everything (the hashing suite needs an unrelated optional dependency)
.\.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/test_hashing.py
```

### Build the ML-ready observation dataset (Day 5A)
```powershell
# Standardise + quality-filter the real exports into the ML-ready schema.
# Raw files in data/ndvi are opened read-only and never modified.
.\.venv\Scripts\python.exe scripts\prepare_ml_dataset.py

# Outputs:
#   data/features/observations_clean.csv
#   data/features/observations_quality_report.json
```

### Build parcel-level features (Day 5B)
```powershell
# One descriptive feature record per parcel inside the commitment window
# configured in backend/ml/processing_config.json (inclusive start /
# exclusive end, UTC). No labels, no model training, no interpolation.
.\.venv\Scripts\python.exe scripts\build_features.py

# Outputs:
#   data/features/parcel_features.csv
#   data/features/parcel_features_report.json
```

### Export full-season NDVI + valid pixel fraction (requires Copernicus auth)
```powershell
# Full pipeline (3 batch jobs: NDVI + valid + eligible coverage):
.\.venv\Scripts\python.exe scripts\export_ndvi.py            # writes to _quality.csv if target exists
.\.venv\Scripts\python.exe scripts\export_ndvi.py --force    # overwrite the target CSV
.\.venv\Scripts\python.exe scripts\export_ndvi.py --dry-run  # build + serialize + check graphs (NO auth, NO job)

# Reuse an existing, configuration-compatible NDVI export and run ONLY the
# two coverage jobs (used for the full season on 2026-10-19):
.\.venv\Scripts\python.exe scripts\export_ndvi.py --reuse-ndvi data/ndvi/parcel_01_2024.csv

# June 2024 test window (already executed; same commands):
.\.venv\Scripts\python.exe scripts\export_ndvi.py --config backend/ml/processing_config_june_2024.json
```

Raw openEO downloads are stored in `data/ndvi/_staging/`, named after the
config's `output_csv` stem (e.g. `parcel_01_2024_coverage_valid_raw.csv`,
`parcel_01_june_2024_ndvi_raw.csv`), so different configs never overwrite each
other's raw data.

**Note:** `--dry-run` does **not** require authentication: it builds the three
processing graphs, writes them to `data/ndvi/_staging/graphs/`, checks every
process against the backend's published process list and requests server-side
graph validation. Static validation does not prove server-side execution will
succeed — that is only confirmed by a real batch job. The live export
(`scripts/export_ndvi.py` without `--dry-run`) requires OIDC authentication to
Copernicus Data Space; the stored refresh token is reused silently when valid,
otherwise a browser login is opened. If auth is not available, inspect the
existing CSVs instead (`parcel_01_2024_quality.csv` and
`parcel_01_june_2024_quality.csv` carry live pixel fractions; the older
`parcel_01_2024.csv` / `parcel_01_june_2024.csv` carry NDVI only).

## 9. Live Export Results (executed 2026-10-19)

Both live exports completed against the Copernicus openEO backend. All values
below are real measurements, not fixtures. Raw downloads are retained in
`data/ndvi/_staging/`.

### June 2024 test window (`processing_config_june_2024.json`, 2024-06-01 → 2024-07-01)

Three batch jobs finished successfully (NDVI, valid-flag mean, eligible-flag
mean). Output: `data/ndvi/parcel_01_june_2024_quality.csv`.

| Metric | Value |
|---|---|
| Acquisitions exported | 6 (2024-06-01, 06, 11, 16, 21, 26) |
| `valid_pixel_fraction` | 1.0 on every date (cloud-free June over the parcel) |
| NDVI range | 0.1993 – 0.6080 |

Cross-check: the six June NDVI values are byte-identical to the corresponding
rows of the pre-existing full-season export, confirming the NDVI graph is
reproducible across independent runs.

### Full season (`processing_config.json`, 2024-03-01 → 2024-11-01 exclusive)

The NDVI series was reused from the existing real export
(`parcel_01_2024.csv`, configuration-compatible) via `--reuse-ndvi`; only the
two coverage jobs were run. Output: `data/ndvi/parcel_01_2024_quality.csv`.

| Metric | Value |
|---|---|
| Total acquisitions | 48 (2024-03-03 → 2024-10-29) |
| Observations with NDVI | 35 |
| Clouded acquisitions (NDVI `NaN`, fraction 0.0) | 13 |
| Quality-valid observations (fraction ≥ 0.50) | 29 |
| Quality-excluded (0 < fraction < 0.50) | 6 |
| `valid_pixel_fraction` values observed | 0.0, 0.0137, 0.0558, 0.0956, 0.1785, 0.3701, 0.4011, 0.6598, 0.6997, 0.7783, 0.9046, 0.9958, 1.0 |
| Temporal coverage (10-day intervals) | 0.76 (19/25 intervals) |
| Evidence quality | `assessed` |
| Provisional verdict (0.35 NDVI / 0.80 fraction policy) | `nonconform` — 10/29 observations above threshold (0.34 < 0.80) |

The verdict is driven by the genuine post-June decline (harvest / bare soil),
not by missing data: all 13 clouded acquisitions and all 6 low-fraction
acquisitions were excluded by the structural and pixel-quality rules before
classification. Full details in `data/features/parcel_01_provisional_result.json`.

## 10. Configuration & Reproducibility

All processing parameters are stored in `backend/ml/processing_config.json`
(full season) and `backend/ml/processing_config_june_2024.json` (June test
window). Key fields:
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

## 11. ML-Ready Observation Dataset (Day 5A)

`scripts/prepare_ml_dataset.py` turns the real exports into a single
standardised, quality-filtered dataset:

```text
parcel_id, acquired_at, scene_id, ndvi_mean, valid_pixel_fraction
```

Outputs (regenerated deterministically from the raw exports):

- `data/features/observations_clean.csv` — accepted observations only
- `data/features/observations_quality_report.json` — counts, exclusion
  reasons, per-parcel accounting, date ranges, dataset SHA-256 and warnings

Processing policy:

- One source file per parcel: `_quality` exports are preferred over
  NDVI-only exports (real quality metadata), full season over the June-only
  test window. Alternate files are reported as skipped and never merged,
  because the June export is a subset of the full season.
- Timestamps are parsed as UTC (pandas `ISO8601`) and written as
  `YYYY-MM-DDTHH:MM:SSZ`; missing/unparseable timestamps are excluded.
- Missing or out-of-range NDVI is excluded (never imputed). Missing NDVI on a
  clouded acquisition is a structural exclusion, not a fabricated value.
- Duplicate `(parcel_id, acquired_at)` rows are removed deterministically
  (first occurrence in the source file).
- Rule C is applied through the existing
  `backend.ml.quality.filter_observations_by_quality()` with
  `min_valid_pixel_fraction` from `processing_config.json` (0.50). Missing
  quality metadata is treated as insufficient, never as valid.
- Accepted observations are sorted chronologically (ties by `parcel_id`).

Real result on the current data (2026-10-19 run):

| Metric | Value |
|---|---|
| Source | `data/ndvi/parcel_01_2024_quality.csv` (preferred over 4 alternate files) |
| Original observations | 48 |
| Accepted observations | 29 |
| Excluded observations | 19 (13 missing/clouded NDVI + 6 below 0.50) |
| Unique parcels | 1 (`parcel_01`) |
| Accepted date range | 2024-03-23 → 2024-10-24 |
| Dataset SHA-256 | `38ef773ccda3c6d48c9b56906c54f2bc84315d8e525853a9f4ab28966b7952e6` |

These counts match the Day 4 verification (`29` quality-valid observations),
confirming the dataset is derived from the same real measurements. The
`scene_id` column is empty because the aggregated openEO export does not
expose scene identifiers (never fabricated). Raw files were verified
byte-identical (SHA-256) before and after the run.

## 12. Parcel Feature Engineering (Day 5B)

`backend/ml/features.py` (driver: `scripts/build_features.py`) converts the
quality-approved observations from §11 into **one descriptive feature record
per parcel** within the configured commitment window:

```text
parcel_id, ndvi_mean, ndvi_min, ndvi_max, ndvi_std, ndvi_range, ndvi_trend,
observation_count, observation_span_days, mean_valid_pixel_fraction,
min_valid_pixel_fraction
```

Outputs (regenerated deterministically from `observations_clean.csv`):

- `data/features/parcel_features.csv` — one row per parcel
- `data/features/parcel_features_report.json` — diagnostics per parcel
  (counts, distinct dates, span, quality metadata, evidence sufficiency),
  feature units, input/output SHA-256, warnings and the grouping limitation

Feature definitions:

- `ndvi_std` uses the **population** convention (`ddof=0`): the accepted
  observations in the window are treated as the complete set, not a sample.
- `ndvi_trend` is an ordinary-least-squares slope of NDVI against **elapsed
  days since the first distinct acquisition date** (NDVI units / day). It is
  `null` when fewer than two distinct observation dates exist; dates are never
  invented and missing dates are never interpolated.
- `observation_count` counts accepted observations; `observation_span_days` is
  the number of days between the first and last accepted acquisition.
- `mean_valid_pixel_fraction` / `min_valid_pixel_fraction` come only from real
  `valid_pixel_fraction` values.

Safeguards:

- The commitment window uses the existing convention (inclusive start,
  exclusive end, UTC) sourced from `processing_config.json`; an invalid window
  raises instead of silently widening the selection.
- When `valid_pixel_fraction` is present, Rule C is re-applied defensively
  through the existing `backend.ml.quality.filter_observations_by_quality()`
  (no duplicated logic and no changed thresholds). When the whole column is
  absent, NDVI features are still computed but the quality features are `null`
  and `quality_metadata_available` is `false`.
- No labels, no rule verdicts (`conform`/`nonconform`/`inconclusive`) and no
  model training are involved. Missing measurements are excluded, never
  imputed; no synthetic parcel is created.
- Parcels with fewer than `min_valid_observations` (5) accepted observations
  keep their descriptive features but are marked
  `evidence_sufficiency: "insufficient"` and do not qualify for compliance
  verification. The verifier's thresholds are unchanged.
- Multi-period limitation: features are grouped by `parcel_id` only. With more
  than one commitment period the grouping key must become
  `(parcel_id, window_start, window_end)` so periods are never combined
  silently (documented in the report).

Real result on the current data (2026-10-19 run):

| Feature | Value |
|---|---|
| `parcel_id` | `parcel_01` |
| `ndvi_mean` | 0.394553 |
| `ndvi_min` | 0.151147 |
| `ndvi_max` | 0.920044 |
| `ndvi_std` (population) | 0.287082 |
| `ndvi_range` | 0.768897 |
| `ndvi_trend` | -0.003755 NDVI/day |
| `observation_count` | 29 |
| `observation_span_days` | 215.0 |
| `mean_valid_pixel_fraction` | 0.966834 |
| `min_valid_pixel_fraction` | 0.6598 |

| Metric | Value |
|---|---|
| Parcels processed | 1 (`parcel_01`) |
| Feature records | 1 |
| Observations used | 29 (window 2024-03-01 → 2024-11-01 exclusive) |
| Independent recomputation | matches exactly |
| Dataset SHA-256 | `b29ee3ab8a05181ed36a78a0f3a4ce0095df1b461bb33b3f0c6d5de0922c216a` |

Because only one parcel exists, **supervised generalization cannot be
evaluated** and rows from the same parcel are not independent samples. This is
a documented limitation, not a modelling claim.

## 13. Current Limitations

1. **Pixel fraction — now measured, not pending**: Live `valid_pixel_fraction`
   values exist for the full season (`parcel_01_2024_quality.csv`) and for the
   June test window (`parcel_01_june_2024_quality.csv`); `verify_parcel()`
   prefers these exports and enforces Rule C on real measurements
   (`evidence_quality: "assessed"`). The older NDVI-only exports
   (`parcel_01_2024.csv`, `parcel_01_june_2024.csv`) remain untouched as raw
   data and are still supported with `evidence_quality: "unknown"` when used.
2. **Commitment-window filtering and temporal coverage**: When the policy supplies a valid commitment window (`window_start`/`window_end`, UTC, inclusive start / exclusive end), only observations inside that window are evaluated, and temporal coverage (Rule B) is computed over it. An explicitly supplied but invalid window (one boundary missing, unparseable date, or `window_end <= window_start`) causes `verify_parcel()` to return `inconclusive` with `reason_code: "INVALID_INPUT"` and it never silently falls back to evaluating the whole dataset. If no window keys are provided at all, the legacy unrestricted mode is preserved (the entire CSV is evaluated) but flagged with warnings that the result is experimental and not settlement-ready. In that case temporal coverage is not enforced.
3. **Coverage export reuse**: `--reuse-ndvi <csv>` re-runs only the two
   coverage jobs against a configuration-compatible existing NDVI export. The
   compatibility requirement is honest: NDVI and coverage must come from the
   same collection, SCL policy and geometry. Compatibility was confirmed for
   the full-season reuse by comparing the June rows of both exports
   (byte-identical NDVI values).
4. **Scene IDs**: The aggregated openEO output does not expose individual scene IDs in the CSV. The schema accepts `scene_id` optionally; when missing, it stays empty and is never fabricated.
5. **Agronomic validity**: NDVI cannot demonstrate absence of herbicides, compliance with fertilization rules, or organic certification.

## 14. Corina Integration Notes

Corina's backend should consume:
- **Primary interface:** `verify_parcel(parcel_id, policy, evidence_directory)` from `backend.ml.rules`
- **Extended quality utilities:** `backend.ml.quality` for pixel filtering, temporal coverage calculation, NDVI/SCL primitives, and export merging
- **Processing config:** `backend/ml/processing_config.json` for policy defaults/metadata
- **Evidence format:** See `backend/ml/README.md` for the full return schema. The `quality` block now always includes `evidence_quality`, `quality_excluded_count`, `temporal_coverage`, `covered_intervals`, `total_intervals`, `interval_length_days` and `warnings` (in addition to `valid_count`/`total_rows`/`excluded_count`). When `valid_pixel_fraction` is present in the CSV, each observation also includes it.

**Key integration points:**
- Verdict codes remain 0/1/2 (unchanged). 
- Function never raises exceptions; all error states return `inconclusive` with `reason_code`.
- CSV paths are resolved relative to `evidence_directory`; function prefers `_2024_quality.csv` (real pixel fractions, Rule C enforced), then `_2024.csv`, then the June equivalents, then `_clean.csv`.
- Observations are sorted chronologically and deduplicated by date.
- The standard merged export schema (`parcel_id, acquired_at, scene_id,
  ndvi_mean, valid_pixel_fraction`) is accepted directly: `acquired_at` is
  recognized as an alias of `date`, and `band_unnamed` (raw openEO exports) as
  an alias of `ndvi_mean`.

## 15. Reserved for Day 6

- Train/test split by `parcel_id` (GroupKFold) with independent test set.
- LightGBM baseline + evaluation with confusion matrix/F1.
- Labels from `data/labels.csv` integration (see `backend/ml/LABELING.md`).
- Evidence document canonicalization/hashing (separately owned by Corina; schema alignment).

Feature engineering (Day 5B) is complete — see §12.