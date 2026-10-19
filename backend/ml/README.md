# backend/ml/ — Provisional Satellite-Based Vegetation Verification

## Purpose

This module provides a **provisional rule-based vegetation verifier** for the TerraCycle Proof project. It processes real Sentinel-2 satellite observations (NDVI time series) exported from Copernicus Data Space and produces an experimental verification result.

The verifier classifies observations into one of three verdicts:
- **conform** (code 0) — Sufficient observations satisfy the experimental vegetation policy
- **nonconform** (code 1) — Sufficient observations contradict the experimental policy
- **inconclusive** (code 2) — Insufficient evidence to determine compliance

> **IMPORTANT:** This is an experimental prototype. The verdicts are NOT agronomically validated compliance decisions and must NOT authorize blockchain settlement or on-chain payments.

---

## Data Sources

| Component | Description |
|-----------|-------------|
| **Sentinel-2 L2A** | Surface reflectance product from the Copernicus Sentinel-2 mission |
| **B04 (Red)** | Red band reflectance |
| **B08 (NIR)** | Near-infrared band reflectance |
| **SCL** | Scene Classification Layer — pixel-level quality mask |
| **NDVI** | Normalized Difference Vegetation Index: `(B08 - B04) / (B08 + B04)` |
| **Copernicus openEO** | Processing API for accessing and computing Sentinel-2 data |

SCL classes retained for NDVI calculation:
- Class 4: Vegetation
- Class 5: Not-vegetated (bare soil visible)

All other SCL classes (clouds, shadows, water, etc.) are masked out before NDVI aggregation.

---

## Architecture

```
GeoJSON (parcel polygon)
    |
    v
Sentinel-2 L2A via openEO (B04, B08, SCL)
    |
    v
SCL masking (retain classes 4, 5)
    |
    +--> NDVI = (B08 - B04) / (B08 + B04)      --> mean over valid pixels
    |
    +--> valid mask (0/1)                       --> valid_pixel_fraction = mean
    |
    v
CSV export, merged schema (data/ndvi/parcel_01_2024.csv)
    parcel_id, acquired_at, scene_id, ndvi_mean, valid_pixel_fraction
    |
    v
Data validation (timestamps, NDVI range, duplicates)
    |
    v
Quality gating (backend/ml/quality.py)
    - Rule C: drop observations with valid_pixel_fraction < 0.50
    - Rule B: temporal coverage over fixed 10-day intervals
    |
    v
Provisional rule-based verification (backend/ml/rules.py::verify_parcel)
    |
    v
JSON result (data/features/parcel_01_provisional_result.json)
```

---

## Instructions (Windows PowerShell)

### Setup

```powershell
# From the repository root
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-ml.txt
pip install pytest
```

### Validate Parcel

```powershell
.\.venv\Scripts\python.exe scripts\check_parcel.py
```

### Inspect NDVI Data

```powershell
.\.venv\Scripts\python.exe scripts\inspect_ndvi.py
```

### Run Provisional Verification

```powershell
.\.venv\Scripts\python.exe scripts\run_real_verification.py
```

### Run Tests

```powershell
# Original test script (6 synthetic scenarios)
.\.venv\Scripts\python.exe tests\test_rules.py

# Comprehensive rules suite (44 tests)
.\.venv\Scripts\python.exe -m pytest tests\test_rules_pytest.py -v

# Day 4 quality / coverage / export-merge suite (42 tests)
.\.venv\Scripts\python.exe -m pytest tests\test_quality.py -v

# Everything (86 tests)
.\.venv\Scripts\python.exe -m pytest tests\ -q
```

### Export New Satellite Data (requires Copernicus authentication)

```powershell
.\.venv\Scripts\python.exe scripts\export_ndvi.py            # non-destructive (writes _quality.csv if target exists)
.\.venv\Scripts\python.exe scripts\export_ndvi.py --force    # overwrite target CSV
.\.venv\Scripts\python.exe scripts\export_ndvi.py --dry-run  # build the openEO graph without running a job
```

The export reads all parameters from `backend/ml/processing_config.json`, computes
both `ndvi_mean` (valid pixels only) and `valid_pixel_fraction` (accepted mask mean
over the whole parcel), and merges them into the standard schema. It never overwrites
an existing successful output unless `--force` is given.

> Runnable pipeline scripts live in `scripts/` and tests in `tests/`.
> All scripts anchor their paths to the repository root, so they work
> when invoked from the repository root as shown above.

---

## Verification Rules

### Experimental Thresholds

| Parameter | Value | Description |
|-----------|-------|-------------|
| `ndvi_threshold` | **0.35** | NDVI above this value is classified as "vegetated" |
| `required_fraction` | **0.80** (80%) | Minimum fraction of vegetated observations for `conform` |
| `min_observations` | **5** | Minimum valid observations required for a verdict (Rule A) |
| `min_valid_pixel_fraction` | **0.50** | Minimum valid-pixel fraction per observation (Rule C) |
| `min_temporal_coverage` | **0.50** | Minimum temporal coverage over the window (Rule B) |
| `temporal_coverage_interval_days` | **10** | Fixed interval length for temporal coverage |

All values come from `backend/ml/processing_config.json`.

### Decision Logic

1. **Commitment window (filter)**: If the policy provides BOTH `window_start`
   and `window_end`, keep only rows whose acquisition timestamp satisfies
   `window_start <= acquired_at < window_end` — **inclusive start, exclusive
   end**, compared in **UTC** (both bounds are parsed with `utc=True`). This
   filter runs *before* every other rule (structural, pixel quality,
   coverage, counting, classification), so no observation outside the
   committed period can influence the verdict.
   - Explicitly supplied but **invalid** window — one boundary missing,
     unparseable date, or `window_end <= window_start` — → `inconclusive`
     (`reason_code: "INVALID_INPUT"`). The verifier never silently falls back
     to evaluating the whole dataset when a window was requested.
   - Valid window that contains **zero** rows → `inconclusive`
     (`reason_code: "INSUFFICIENT_OBSERVATIONS"`).
   - **No window keys at all** → legacy unrestricted mode (see Limitations):
     the whole CSV is evaluated and an explicit warning marks the result as
     experimental and not settlement-ready.
2. **Filter (structural)**: Remove observations with `None`, `NaN`, or NDVI outside `[-1, 1]`
3. **Quality gate (Rule C)**: If the CSV has a `valid_pixel_fraction` column, drop
   observations whose fraction is `< min_valid_pixel_fraction` (or missing). If the
   column is absent, no observation is dropped but `evidence_quality` is reported as
   `"unknown"`.
4. **Temporal coverage (Rule B)**: If the policy provides `window_start` and
   `window_end`, compute coverage over fixed 10-day intervals (same
   inclusive-start/exclusive-end boundary convention as the window filter).
   Coverage `< min_temporal_coverage` → `inconclusive` (`INSUFFICIENT_TEMPORAL_COVERAGE`).
5. **Count (Rule A)**: If fewer than `min_observations` quality-valid values remain → `inconclusive`
6. **Classify**: Count how many quality-valid observations have NDVI > `ndvi_threshold`
7. **Decide**:
   - If `vegetated_count / valid_count >= required_fraction` → `conform`
   - Otherwise → `nonconform`

Temporal coverage is `intervals_with_valid_observations / total_intervals`. An
interval is covered if it contains at least one valid observation; several
observations in the same interval count once.

> [!IMPORTANT]
> The NDVI classification (steps 3–7) is an **experimental vegetation
> classification**, not evidence-supported compliance. A `conform` verdict is
> only meaningful together with assessed evidence quality
> (`evidence_quality: "assessed"`, i.e. real `valid_pixel_fraction`
> measurements). While the committed real CSVs lack that column,
> `evidence_quality` is `"unknown"` and the verdict — whatever it is — must
> not be presented as settlement-ready verification.

### Verdict Mapping (EIP-712/Solidity)

| Verdict | Code | Meaning |
|---------|------|---------|
| `conform` | 0 | Observations satisfy the experimental policy |
| `nonconform` | 1 | Observations contradict the experimental policy |
| `inconclusive` | 2 | Insufficient data; no claim about the practice |

---

## Real Satellite Results (June–October 2024)

The following are **actual observations from Copernicus Sentinel-2 L2A**, exported via openEO for parcel_01 (Dolj region, Romania):

- **Source file**: `data/ndvi/parcel_01_2024.csv`
- **Total rows**: 48 (of which 13 had missing NDVI due to cloud masking)
- **Valid observations**: 35
- **Period**: 2024-03-03 to 2024-10-29
- **NDVI range**: 0.1053 to 0.9200
- **NDVI mean**: 0.4044
- **NDVI median**: 0.2157
- **Temporal coverage**: 0.92 (23/25 intervals of 10 days over 2024-03-01..2024-11-01)
- **Evidence quality**: `unknown` — this CSV predates the `valid_pixel_fraction`
  column, so Rule C could not be applied (see Limitations).

### Provisional Verdict

- **Verdict**: `nonconform` (code 1)
- **Reason**: 13/35 observations above NDVI threshold 0.35 (fraction=0.37, required=0.80)
- **Validation status**: `experimental_only`

The data shows high NDVI in March–May (vegetation season) followed by a sharp decline from June onwards, consistent with harvest or crop change. The commitment window used for this run comes from `processing_config.json` (`2024-03-01` .. `2024-11-01`, inclusive start / exclusive end, UTC) and covers the whole CSV, so commitment-window filtering excludes no observation here; the post-June decline is what explains why most observations fall below the vegetation threshold.

---

## Limitations

> [!WARNING]
> The following limitations apply to ALL outputs of this module.

1. **Pixel validity fraction** (`valid_pixel_fraction`) support is implemented in the
   export pipeline (`scripts/export_ndvi.py`) and in the verifier, but the real CSVs
   currently committed under `data/ndvi/` predate the change and do not contain the
   column. Live values require a Copernicus-authenticated re-export, which has not been
   run. Until then, the verifier reports `evidence_quality: "unknown"`, does not apply
   Rule C, and adds an explicit warning that the result is experimental and must not
   be treated as settlement-ready verification.
   The merge logic is covered by offline tests using mocked openEO outputs.

2. **Commitment-window filtering** is applied whenever the policy supplies both
   `window_start` and `window_end`: only observations with
   `window_start <= acquired_at < window_end` (inclusive start, exclusive end,
   UTC) are evaluated, and the same window bounds Rule B's coverage computation.
   The window is taken from `processing_config.json` (`time_interval`). An
   explicitly supplied but invalid window (one boundary missing, unparseable
   date, or `window_end <= window_start`) returns `inconclusive`
   (`INVALID_INPUT`) instead of evaluating the whole dataset; an empty valid
   window returns `inconclusive` (`INSUFFICIENT_OBSERVATIONS`). Only policies
   with *no* window keys at all fall back to the legacy unrestricted mode,
   which is flagged experimental / not settlement-ready via `warnings`.
   Temporal coverage (Rule B) is computed and enforced whenever that valid
   window exists; observations with missing dates and intervals with no valid
   observation are handled deterministically.

3. **Demonstration polygon** may include multiple agricultural fields. The parcel boundary was manually digitized and has not been verified against cadastral records.

4. **Experimental thresholds** (NDVI > 0.35, fraction ≥ 0.80, minimum 5 observations) are working hypotheses, not agronomically validated criteria.

5. **Manual labels** have not yet been collected. The labeling protocol exists (`LABELING.md`) but the `data/labels.csv` file is empty.

6. **LightGBM** has not been trained. The current verifier uses only deterministic rules.

7. **NDVI cannot demonstrate** the absence of herbicides, compliance with fertilization rules, or organic certification. Vegetation presence ≠ sustainable practice.

8. **Provisional results must NOT authorize blockchain settlement.** The `validation_status: experimental_only` field explicitly marks all outputs as non-final.

---

## Next Steps (October 16+)

| Day | Deliverable |
|-----|-------------|
| 16 | ✅ Cloud mask quality metrics, valid pixel fraction pipeline, temporal coverage |
| 17 | Manual labeling with team (15–20 examples each), `labels.csv` |
| 18 | Feature engineering, baseline + LightGBM (if labels justify) |
| 19 | `verify_parcel()` with full evidence and temporal window filtering |
| 20 | Evaluation without leakage, integration test with Corina |
| 21–22 | Real data for all demo scenarios, frozen model/policy |
| 23 | `docs/model.md` and `docs/limitations.md`; feature freeze |

> Day 16 status: quality module, processing config, temporal coverage and the
> integrated rules are implemented and tested. The only pending item is a live
> Copernicus re-export to populate real `valid_pixel_fraction` values.

---

## Integration Contract for Corina

### Import Path

```python
from backend.ml.rules import verify_parcel
```

### Function Signature

```python
def verify_parcel(
    parcel_id: str,
    policy: dict[str, Any],
    evidence_directory: str,
) -> dict[str, Any]:
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `parcel_id` | `str` | Parcel identifier (e.g., `"parcel_01"`) |
| `policy` | `dict` | Verification policy. Optional keys: `ndvi_threshold` (0.35), `required_fraction` (0.80), `min_observations` (5), `min_valid_pixel_fraction` (0.50), `min_temporal_coverage` (0.50), `temporal_coverage_interval_days` (10), `window_start` (ISO date), `window_end` (ISO date, exclusive) |
| `evidence_directory` | `str` | Path to directory containing NDVI CSV files (e.g., `"data/ndvi"`) |

Rule B is applied only when both `window_start` and `window_end` are provided; the same pair activates commitment-window filtering (inclusive start / exclusive end, UTC). An explicitly supplied but invalid window (one boundary missing, unparseable date, or `window_end <= window_start`) returns `inconclusive` with `INVALID_INPUT`; it never degrades into a full-dataset evaluation. Policies with no window keys keep the legacy unrestricted behaviour (experimental, not settlement-ready).
Rule C is applied only when the CSV contains a `valid_pixel_fraction` column.

### Return Value

```python
{
    "verdict": "conform" | "nonconform" | "inconclusive",
    "verdict_code": 0 | 1 | 2,
    "reason_code": "RULE_BASED_DECISION" | "INSUFFICIENT_OBSERVATIONS"
                 | "INSUFFICIENT_TEMPORAL_COVERAGE" | "MISSING_EVIDENCE"
                 | "CSV_READ_ERROR" | "INVALID_CSV_STRUCTURE" | "INVALID_INPUT",
    "reason": "Human-readable explanation of the verdict",
    "observations": [
        {
            "acquired_at": "2024-04-01T00:00:00Z",
            "ndvi_mean": 0.6543,
            "is_valid_observation": True,
            # "valid_pixel_fraction": 0.92,      (when available)
            # "quality_reason": "..."            (only when excluded)
        },
        ...
    ],
    "quality": {
        "valid_count": 35,
        "total_rows": 48,
        "excluded_count": 13,
        "structural_excluded_count": 13,
        "quality_excluded_count": 0,
        "vegetated_count": 13,
        "vegetated_fraction": 0.3714,
        "quality_metadata_available": False,
        "evidence_quality": "assessed" | "unknown",
        "min_valid_pixel_fraction": 0.5,
        "temporal_coverage": 0.92,
        "covered_intervals": 23,
        "total_intervals": 25,
        "interval_length_days": 10,
        "inconclusive_reason": null | "INSUFFICIENT_OBSERVATIONS"
                            | "INSUFFICIENT_TEMPORAL_COVERAGE" | "INVALID_INPUT",
        "warnings": ["valid_pixel_fraction missing; pixel-quality rule (Rule C) not applied"]
    },
    "model": {
        "model_version": "rule-based-v1",
        "features_version": null,
        "source": "RULE_BASED",
        "thresholds": {
            "ndvi_threshold": 0.35,
            "required_fraction": 0.80,
            "min_observations": 5,
            "min_valid_pixel_fraction": 0.5,
            "min_temporal_coverage": 0.5,
            "temporal_coverage_interval_days": 10,
            "window_start": "2024-03-01",
            "window_end": "2024-11-01"
        }
    },
    "source": {
        "provider": "Copernicus Data Space",
        "dataset": "Sentinel-2 L2A",
        "method": "cloud-masked NDVI (SCL classes 4,5)",
        "csv_file": "data/ndvi/parcel_01_2024.csv"
    }
}
```

### All Possible Verdicts

| Verdict | Code | When |
|---------|------|------|
| `conform` | 0 | ≥ `required_fraction` of quality-valid observations have NDVI > `ndvi_threshold` |
| `nonconform` | 1 | < `required_fraction` vegetated, with ≥ `min_observations` valid and sufficient temporal coverage |
| `inconclusive` | 2 | < `min_observations` valid, insufficient temporal coverage, missing CSV, read error, invalid structure, or invalid commitment window (`INVALID_INPUT`) |

### Error Handling

- **No CSV file found**: Returns `inconclusive` with `reason_code: "MISSING_EVIDENCE"`
- **CSV read error**: Returns `inconclusive` with `reason_code: "CSV_READ_ERROR"`
- **Missing columns**: Returns `inconclusive` with `reason_code: "INVALID_CSV_STRUCTURE"`
- **Insufficient observations**: Returns `inconclusive` with `reason_code: "INSUFFICIENT_OBSERVATIONS"`
- **Insufficient temporal coverage**: Returns `inconclusive` with `reason_code: "INSUFFICIENT_TEMPORAL_COVERAGE"`
- **Invalid commitment window**: Returns `inconclusive` with `reason_code: "INVALID_INPUT"` (explicitly supplied window invalid or partially specified, e.g. only one boundary, unparseable date, or `window_end <= window_start`); the verifier never silently falls back to evaluating the whole dataset.
- **The function never raises exceptions** — all error states are returned as `inconclusive` verdicts with descriptive reason codes

### What Remains Provisional

- Live `valid_pixel_fraction` values (pipeline implemented; re-export pending auth)
- Rule-based only (no ML model)
- Thresholds are experimental working hypotheses
- Evidence quality can be `"unknown"` when quality metadata is missing (and in that case the result must not be treated as settlement-ready verification)

### Usage Example

```python
from backend.ml.rules import verify_parcel

result = verify_parcel(
    parcel_id="parcel_01",
    policy={
        "ndvi_threshold": 0.35,
        "required_fraction": 0.80,
        "min_observations": 5,
        "min_valid_pixel_fraction": 0.50,   # Rule C
        "min_temporal_coverage": 0.50,      # Rule B
        "window_start": "2024-03-01",
        "window_end": "2024-11-01",
    },
    evidence_directory="data/ndvi",
)

print(result["verdict"])          # "nonconform"
print(result["verdict_code"])     # 1
print(result["quality"]["temporal_coverage"])  # 0.92
```

### Direct Low-Level Function

The lower-level `verify_vegetation()` is also available for unit testing:

```python
from backend.ml.rules import verify_vegetation

result = verify_vegetation(
    observations=[0.5, 0.6, 0.7, 0.55, 0.65],
    min_observations=5,
    ndvi_threshold=0.35,
    required_fraction=0.80,
)
# result["verdict"] == "conform"
```

> **Note:** Corina's backend should NOT recalculate features or thresholds. The ML module is the single source of truth for verification logic. Corina handles canonical serialization and SHA-256 hashing of the evidence document.
