# Satellite Demo Guide — Day 6B

## Overview

This guide explains how to run the satellite verification for the hackathon demonstration. The verifier uses real Sentinel-2 NDVI data from four agricultural parcels and produces JSON verdicts.

## Prerequisites

```powershell
# Activate the virtual environment (if not already active)
.\.venv\Scripts\Activate.ps1

# Or use the Python executable directly
.\.venv\Scripts\python.exe --version
```

## Running the verifier

### Verify all four parcels

```powershell
.\.venv\Scripts\python.exe scripts\run_verification.py --all
```

This generates four JSON reports in `data/verification/`:
- `parcel_01_verification.json`
- `parcel_02_verification.json`
- `parcel_03_verification.json`
- `parcel_04_verification.json`

### Verify a single parcel

```powershell
.\.venv\Scripts\python.exe scripts\run_verification.py --parcel parcel_01
```

### Custom output directory

```powershell
.\.venv\Scripts\python.exe scripts\run_verification.py --all --output-dir data/my_verification
```

## Current real results

| Parcel | Verdict | Code | Valid observations | Vegetated | Temporal coverage |
|---|---|---|---|---|---|
| parcel_01 | `nonconform` | 1 | 29/48 | 10 (34%) | 0.76 |
| parcel_02 | `nonconform` | 1 | 63/97 | 30 (48%) | 1.00 |
| parcel_03 | `nonconform` | 1 | 62/97 | 31 (50%) | 0.92 |
| parcel_04 | `nonconform` | 1 | 60/97 | 23 (38%) | 0.92 |

## What the verdicts mean

### Verdict types

| Verdict | Code | Meaning |
|---|---|---|
| `conform` | 0 | Observations meet the configured policy (≥80% vegetated, ≥5 observations, ≥50% temporal coverage) |
| `nonconform` | 1 | Sufficient observations exist but the policy condition is NOT met |
| `inconclusive` | 2 | Insufficient evidence — does NOT mean the practice failed |

### Why all four parcels are `nonconform`

All four parcels have sufficient observations and good temporal coverage, but the fraction of observations with NDVI > 0.35 is below the required 0.80 threshold:

- parcel_01: 34% vegetated (need 80%)
- parcel_02: 48% vegetated (need 80%)
- parcel_03: 50% vegetated (need 80%)
- parcel_04: 38% vegetated (need 80%)

This is a **rule-based vegetation classification**, NOT a compliance verdict. It means the satellite data shows significant non-vegetated periods during the growing season (e.g., bare soil between crops, harvest periods).

## What the quality measurements mean

### `valid_pixel_fraction`

Each observation includes `valid_pixel_fraction` = the fraction of pixels in the parcel that passed cloud/shadow filtering (SCL classes 4-5). Values range from 0 (completely cloudy) to 1 (clear). Observations below 0.50 are excluded from the verdict.

### `temporal_coverage`

The commitment window (2024-03-01 to 2024-11-01) is divided into 10-day intervals. Temporal coverage = intervals with at least one valid observation / total intervals. All four parcels have coverage ≥ 0.76.

### `scene_id`

`scene_id` is `null` for all observations because the aggregated openEO export does not expose individual scene identifiers. They are never fabricated.

## What the satellite evidence CAN and CANNOT establish

### CAN establish

- Vegetation presence and approximate density (NDVI) during clear observations
- Temporal patterns of vegetation throughout the growing season
- Cloud-free observation coverage for each parcel

### CANNOT establish

- Organic certification (no pesticide/herbicide data)
- Compliance with fertilization rules
- Specific crop types
- Farming practices
- Ground truth without field visits

**The verdict is an experimental classification, NOT a compliance verdict, and does NOT authorize blockchain settlement.**

## What Corina's frontend should display

For each parcel, show:

1. **Parcel ID** (e.g., "Parcel 01")
2. **Verdict** with color coding:
   - `conform` → green (experimental)
   - `nonconform` → amber (experimental)
   - `inconclusive` → gray (insufficient data)
3. **Vegetated fraction** (e.g., "34% of observations above NDVI threshold")
4. **Valid observation count** (e.g., "29 of 48 observations passed quality filter")
5. **Temporal coverage** (e.g., "76% of 10-day intervals covered")
6. **Evidence quality** badge: "assessed" or "unknown"
7. **Warning banner**: "This is an experimental vegetation assessment, NOT organic certification."

### Example frontend text

```
Parcel 01 — Experimental Result: nonconform
10/29 observations above NDVI 0.35 (34%, required 80%)
Temporal coverage: 76% | Evidence quality: assessed

⚠️ This is a satellite-based vegetation assessment.
It is NOT organic certification and does NOT authorize payment.
```

## Demonstrating an inconclusive result safely

To show how `inconclusive` works without modifying real data, use the Python API with a synthetic parcel:

```python
from backend.ml.rules import verify_parcel

# A parcel with too few observations
result = verify_parcel(
    "parcel_99",  # non-existent parcel
    {
        "window_start": "2024-03-01",
        "window_end": "2024-11-01",
    },
    "data/ndvi",
)
print(result["verdict"])  # "inconclusive"
print(result["reason_code"])  # "MISSING_EVIDENCE"
```

This returns `inconclusive` without crashing, demonstrating safe failure.

## Integration with Corina's backend

The verifier is called as:

```python
from backend.ml.rules import verify_parcel

result = verify_parcel(parcel_id, policy, evidence_directory)
# result is a JSON-serializable dict
```

See `docs/ml-integration-handoff.md` for the complete API reference.

## Running tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/test_hashing.py
```

Expected: 246 passed.
