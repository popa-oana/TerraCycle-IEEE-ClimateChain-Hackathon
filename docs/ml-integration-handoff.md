# ML Integration Handoff — Day 6A

## 1. The callable function

Corina's backend should import and call:

```python
from backend.ml.rules import verify_parcel

result = verify_parcel(
    parcel_id="parcel_01",
    policy={
        "window_start": "2024-03-01",
        "window_end": "2024-11-01",
        "ndvi_threshold": 0.35,
        "required_fraction": 0.80,
        "min_observations": 5,
        "min_valid_pixel_fraction": 0.50,
        "min_temporal_coverage": 0.50,
        "temporal_coverage_interval_days": 10,
    },
    evidence_directory="data/ndvi",
)
```

This is the **single source of truth**. Do not reimplement verification logic in FastAPI.

## 2. Parameters

| Parameter | Type | Description |
|---|---|---|
| `parcel_id` | `str` | One of `"parcel_01"`, `"parcel_02"`, `"parcel_03"`, `"parcel_04"` |
| `policy` | `dict` | Verification policy (see below) |
| `evidence_directory` | `str` | Directory containing `{parcel_id}_2024_quality.csv` |

### Policy keys

| Key | Default | Description |
|---|---|---|
| `window_start` | `"2024-03-01"` | Commitment window start (inclusive, UTC) |
| `window_end` | `"2024-11-01"` | Commitment window end (exclusive, UTC) |
| `ndvi_threshold` | `0.35` | NDVI above which an observation is "vegetated" |
| `required_fraction` | `0.80` | Minimum fraction of vegetated observations for `conform` |
| `min_observations` | `5` | Minimum valid observations for a verdict |
| `min_valid_pixel_fraction` | `0.50` | Rule C: minimum pixel quality per observation |
| `min_temporal_coverage` | `0.50` | Rule B: minimum temporal coverage |
| `temporal_coverage_interval_days` | `10` | Interval length for coverage calculation |

All thresholds come from `backend/ml/processing_config.json`. Do not hardcode them in the backend.

## 3. Input schema

CSV files in `evidence_directory` must contain at minimum:

```
date,ndvi_mean
```

Or the standard export schema:

```
parcel_id,acquired_at,scene_id,ndvi_mean,valid_pixel_fraction
```

The function accepts `date`/`acquired_at` aliases and `band_unnamed`/`ndvi_mean` aliases.

## 4. Output JSON structure

```json
{
  "verdict": "conform | nonconform | inconclusive",
  "verdict_code": 0 | 1 | 2,
  "reason_code": "RULE_BASED_DECISION | INSUFFICIENT_OBSERVATIONS | INSUFFICIENT_TEMPORAL_COVERAGE | MISSING_EVIDENCE | INVALID_CSV_STRUCTURE | CSV_READ_ERROR | INVALID_INPUT",
  "reason": "human-readable explanation",
  "observations": [
    {
      "acquired_at": "2024-04-01T00:00:00Z",
      "ndvi_mean": 0.54,
      "is_valid_observation": true,
      "valid_pixel_fraction": 0.93
    }
  ],
  "quality": {
    "valid_count": 29,
    "total_rows": 48,
    "excluded_count": 19,
    "quality_excluded_count": 6,
    "vegetated_count": 10,
    "vegetated_fraction": 0.34,
    "quality_metadata_available": true,
    "evidence_quality": "assessed",
    "temporal_coverage": 0.76,
    "covered_intervals": 23,
    "total_intervals": 31,
    "interval_length_days": 10,
    "warnings": []
  },
  "model": {
    "model_version": "rule-based-v1",
    "source": "RULE_BASED",
    "thresholds": {}
  },
  "source": {
    "provider": "Copernicus Data Space",
    "dataset": "Sentinel-2 L2A",
    "csv_file": "data/ndvi/parcel_01_2024_quality.csv"
  }
}
```

The output is fully JSON-serializable with `json.dumps(result)`.

## 5. Verdict mapping

| Verdict | Code | Meaning |
|---|---|---|
| `conform` | 0 | Observations meet the configured policy |
| `nonconform` | 1 | Sufficient observations, policy condition not met |
| `inconclusive` | 2 | Insufficient evidence; does NOT mean the practice failed |

## 6. Error handling

The function **never raises exceptions** for invalid inputs. It returns `inconclusive` with a specific `reason_code`:

| Condition | `reason_code` |
|---|---|
| Invalid window (unparseable, inverted, missing boundary) | `INVALID_INPUT` |
| No CSV found for parcel | `MISSING_EVIDENCE` |
| CSV has wrong columns | `INVALID_CSV_STRUCTURE` |
| CSV unreadable | `CSV_READ_ERROR` |
| No valid observations in window | `INSUFFICIENT_OBSERVATIONS` |
| Temporal coverage below threshold | `INSUFFICIENT_TEMPORAL_COVERAGE` |

## 7. Commitment window semantics

- **Inclusive start, exclusive end**: `window_start <= acquired_at < window_end`
- All timestamps are UTC
- Window filtering happens BEFORE classification, counting, and evidence assembly
- An invalid window returns `inconclusive` with `INVALID_INPUT` — it never silently falls back to evaluating the whole dataset

## 8. Vegetation verdict vs. evidence sufficiency vs. settlement authorization

These are **three distinct concepts**:

1. **Vegetation verdict** (`verdict`): Does the NDVI data meet the configured policy thresholds? This is an experimental classification, NOT a compliance verdict.

2. **Evidence sufficiency** (`evidence_quality`): Is the data complete enough to make a verdict? Values: `"assessed"` (real `valid_pixel_fraction` data available) or `"unknown"` (no quality metadata). When unknown, the result is explicitly flagged as experimental and non-settlement-ready.

3. **Settlement authorization**: This verifier does NOT produce settlement authorization. The result must be reviewed by an authorized verifier and signed via EIP-712 before any blockchain settlement. The backend must verify the receipt, contract, chainId, method, parameters, and events — not trust a verdict string.

## 9. Known limitations

- **`scene_id` is null**: The aggregated openEO export does not expose scene identifiers. They are never fabricated.
- **NDVI is not organic certification**: The verdict indicates vegetation presence from satellite data only. It cannot demonstrate absence of herbicides, compliance with fertilization rules, or organic certification.
- **Manual digitization**: Parcel polygons may include multiple agricultural fields; the dataset cannot separate fields inside a polygon.
- **Small sample**: 4 parcels is insufficient for supervised generalization.

## 10. Reproduction commands

```powershell
# Verify a single parcel
.\.venv\Scripts\python.exe scripts\run_verification.py --parcel parcel_01

# Verify all four parcels
.\.venv\Scripts\python.exe scripts\run_verification.py --all

# Run all tests
.\.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/test_hashing.py
```

Reports are written to `data/verification/{parcel_id}_verification.json`.
