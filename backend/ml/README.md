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
    v
NDVI = (B08 - B04) / (B08 + B04)
    |
    v
Spatial aggregation (mean per parcel per date)
    |
    v
CSV export (data/ndvi/parcel_01_2024.csv)
    |
    v
Data validation (timestamps, NDVI range, duplicates)
    |
    v
Provisional rule-based verification (backend/ml/rules.py)
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

# Comprehensive pytest suite (44 tests)
.\.venv\Scripts\python.exe -m pytest tests\test_rules_pytest.py -v
```

### Export New Satellite Data (requires Copernicus authentication)

```powershell
.\.venv\Scripts\python.exe scripts\export_ndvi.py
```

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
| `min_observations` | **5** | Minimum valid observations required for a verdict |

### Decision Logic

1. **Filter**: Remove observations with `None`, `NaN`, or NDVI outside `[-1, 1]`
2. **Count**: If fewer than `min_observations` valid values remain → `inconclusive`
3. **Classify**: Count how many valid observations have NDVI > `ndvi_threshold`
4. **Decide**:
   - If `vegetated_count / valid_count >= required_fraction` → `conform`
   - Otherwise → `nonconform`

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

### Provisional Verdict

- **Verdict**: `nonconform` (code 1)
- **Reason**: 13/35 observations above NDVI threshold 0.35 (fraction=0.37, required=0.80)
- **Validation status**: `experimental_only`

The data shows high NDVI in March–May (vegetation season) followed by a sharp decline from June onwards, consistent with harvest or crop change. The provisional verifier evaluates the **entire available period**, not a specific committed window — which explains why most observations fall below the vegetation threshold.

---

## Limitations

> [!WARNING]
> The following limitations apply to ALL outputs of this module.

1. **Pixel validity fraction** (`valid_pixel_fraction`) is not yet available in the CSV. The openEO export aggregates spatially but does not separately export the fraction of cloud-free pixels per date.

2. **Complete temporal coverage** has not been validated. The quality metric described in Role_Crenguta.md §6 (splitting the window into weekly intervals and measuring coverage) is not yet implemented.

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
| 16 | Cloud mask quality metrics, valid pixel fraction, temporal coverage |
| 17 | Manual labeling with team (15–20 examples each), `labels.csv` |
| 18 | Feature engineering, baseline + LightGBM (if labels justify) |
| 19 | `verify_parcel()` with full evidence and temporal window filtering |
| 20 | Evaluation without leakage, integration test with Corina |
| 21–22 | Real data for all demo scenarios, frozen model/policy |
| 23 | `docs/model.md` and `docs/limitations.md`; feature freeze |

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
| `policy` | `dict` | Verification policy. Optional keys: `ndvi_threshold` (float, default 0.35), `required_fraction` (float, default 0.80), `min_observations` (int, default 5) |
| `evidence_directory` | `str` | Path to directory containing NDVI CSV files (e.g., `"data/ndvi"`) |

### Return Value

```python
{
    "verdict": "conform" | "nonconform" | "inconclusive",
    "verdict_code": 0 | 1 | 2,
    "reason_code": "RULE_BASED_DECISION" | "INSUFFICIENT_OBSERVATIONS" | "MISSING_EVIDENCE" | "CSV_READ_ERROR" | "INVALID_CSV_STRUCTURE",
    "reason": "Human-readable explanation of the verdict",
    "observations": [
        {
            "acquired_at": "2024-04-01T00:00:00Z",
            "ndvi_mean": 0.6543,
            # "valid_pixel_fraction": 0.92  (when available)
        },
        ...
    ],
    "quality": {
        "valid_count": 35,
        "total_rows": 48,
        "excluded_count": 13,
        "vegetated_count": 13,
        "vegetated_fraction": 0.3714,
        "inconclusive_reason": null | "INSUFFICIENT_OBSERVATIONS"
    },
    "model": {
        "model_version": "rule-based-v1",
        "features_version": null,
        "source": "RULE_BASED",
        "thresholds": {
            "ndvi_threshold": 0.35,
            "required_fraction": 0.80,
            "min_observations": 5
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
| `conform` | 0 | ≥ `required_fraction` of valid observations have NDVI > `ndvi_threshold` |
| `nonconform` | 1 | < `required_fraction` vegetated, with ≥ `min_observations` valid |
| `inconclusive` | 2 | < `min_observations` valid, missing CSV, read error, or invalid structure |

### Error Handling

- **No CSV file found**: Returns `inconclusive` with `reason_code: "MISSING_EVIDENCE"`
- **CSV read error**: Returns `inconclusive` with `reason_code: "CSV_READ_ERROR"`
- **Missing columns**: Returns `inconclusive` with `reason_code: "INVALID_CSV_STRUCTURE"`
- **Insufficient observations**: Returns `inconclusive` with `reason_code: "INSUFFICIENT_OBSERVATIONS"`
- **The function never raises exceptions** — all error states are returned as `inconclusive` verdicts with descriptive reason codes

### What Remains Provisional

- No temporal window filtering (evaluates all available dates)
- No `valid_pixel_fraction` quality check
- No temporal coverage metric
- Rule-based only (no ML model)
- Thresholds are experimental working hypotheses

### Usage Example

```python
from backend.ml.rules import verify_parcel

result = verify_parcel(
    parcel_id="parcel_01",
    policy={
        "ndvi_threshold": 0.35,
        "required_fraction": 0.80,
        "min_observations": 5,
    },
    evidence_directory="data/ndvi",
)

print(result["verdict"])       # "nonconform"
print(result["verdict_code"])  # 1
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
