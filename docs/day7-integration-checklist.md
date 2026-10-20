# Day 7A — Integration Readiness Checklist

**Branch:** `feat/gpr-chronological-evaluation`
**Generated:** 2026-10-20
**Status:** All deliverables verified, tests passing (335 passed)

---

## For Corina (Backend / FastAPI)

### 1. Callable Verification Function

```python
from backend.ml.rules import verify_parcel

result = verify_parcel(
    parcel_id="parcel_01",  # or parcel_02, parcel_03, parcel_04
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

**Location:** `backend/ml/rules.py` — single entry point, no side effects, returns JSON-serializable dict.

### 2. Required Dependencies

Add to `backend/requirements.txt`:
```
eth_abi>=6.0.0
web3>=8.0.0
```

These are needed for `backend/hashing.py::compute_commitment_id()` (Keccak-256 via `eth_abi.encode`). The virtual environment already has them after `pip install eth_abi web3`.

ML dependencies (already in `requirements-ml.txt`):
```
openeo>=0.28.0
pandas>=2.1.0
numpy>=1.24.0
scikit-learn>=1.3.0
lightgbm>=4.0.0
matplotlib>=3.7.0
joblib>=1.3.0
pytest>=7.4.0
```

### 3. Real Data Locations (all tracked in Git)

| Parcel | NDVI + Quality CSV | GeoJSON |
|--------|-------------------|---------|
| parcel_01 | `data/ndvi/parcel_01_2024_quality.csv` | `data/parcels/parcel_01.geojson` |
| parcel_02 | `data/ndvi/parcel_02_2024_quality.csv` | `data/parcels/parcel_02.geojson` |
| parcel_03 | `data/ndvi/parcel_03_2024_quality.csv` | `data/parcels/parcel_03.geojson` |
| parcel_04 | `data/ndvi/parcel_04_2024_quality.csv` | `data/parcels/parcel_04.geojson` |

All four CSVs contain columns: `parcel_id, acquired_at, scene_id, ndvi_mean, valid_pixel_fraction`
- `scene_id` is `null` (openEO aggregated export does not expose it; never fabricated)
- `valid_pixel_fraction` is real, measured via SCL masking (classes 4,5)

### 4. Expected Verification Response Structure

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

### 5. Error Handling & Evidence Limitations

| Condition | `reason_code` | Verdict |
|-----------|---------------|---------|
| Invalid window (unparseable, inverted, missing boundary) | `INVALID_INPUT` | `inconclusive` |
| No CSV found for parcel | `MISSING_EVIDENCE` | `inconclusive` |
| CSV has wrong columns | `INVALID_CSV_STRUCTURE` | `inconclusive` |
| CSV unreadable | `CSV_READ_ERROR` | `inconclusive` |
| No valid observations in window | `INSUFFICIENT_OBSERVATIONS` | `inconclusive` |
| Temporal coverage below threshold | `INSUFFICIENT_TEMPORAL_COVERAGE` | `inconclusive` |

**Key behaviors:**
- Function **never raises exceptions** for invalid inputs — returns `inconclusive` with specific `reason_code`.
- Commitment window: inclusive start, exclusive end (`window_start <= acquired_at < window_end`).
- Window filtering happens BEFORE classification.
- Invalid window → `inconclusive` with `INVALID_INPUT`; **never silently falls back** to evaluating whole dataset.
- When `valid_pixel_fraction` column is absent: Rule C not applied, `evidence_quality: "unknown"`, warning added.

### 6. Verdict Mapping (Canonical)

| Verdict | Code | Meaning |
|---------|------|---------|
| `conform` | 0 | Observations meet the configured policy |
| `nonconform` | 1 | Sufficient observations, policy condition not met |
| `inconclusive` | 2 | Insufficient evidence; does NOT mean the practice failed |

**These codes match EIP-712 / Solidity exactly.**

### 7. Reproduction Commands

```powershell
# Verify a single parcel
.\.venv\Scripts\python.exe scripts\run_verification.py --parcel parcel_01

# Verify all four parcels
.\.venv\Scripts\python.exe scripts\run_verification.py --all

# Run all tests (including hashing)
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Output reports written to `data/verification/{parcel_id}_verification.json`.

---

## For Oana (Frontend / React)

### 1. ML Charts (PNG, ready to embed)

| Parcel | Path |
|--------|------|
| parcel_01 | `data/ml/plots/parcel_01_trajectory.png` |
| parcel_02 | `data/ml/plots/parcel_02_trajectory.png` |
| parcel_03 | `data/ml/plots/parcel_03_trajectory.png` |
| parcel_04 | `data/ml/plots/parcel_04_trajectory.png` |

All four files tracked in Git, regenerated by `scripts/generate_ml_insights.py`.

### 2. AI Insights JSON (frontend-ready)

**Path:** `data/ml/ai_insights.json` (tracked in Git)

**Structure per parcel:**
```typescript
type ParcelInsight = {
  parcel_id: string;
  observations: { timestamp: string; ndvi: number }[];
  split_date: string;
  gpr_predictions: {
    timestamp: string;
    predicted_ndvi: number;
    predicted_std: number;
    lower_95: number;
    upper_95: number;
  }[];
  persistence_predictions: { timestamp: string; predicted_ndvi: number }[];
  metrics: {
    gpr_mae: number;
    gpr_rmse: number;
    baseline_mae: number;
    baseline_rmse: number;
    observed_interval_coverage: number;
    gpr_better_than_persistence: boolean;  // ALWAYS false
  };
  explanation: string;
  limitations: string[];
};
```

### 3. What Values Are Real vs Experimental

| Category | Source | Description |
|----------|--------|-------------|
| **Real satellite observations** | `observations` array | Genuine Sentinel-2 L2A NDVI from Copernicus Data Space, quality-filtered (SCL classes 4,5), cloud-masked |
| **Experimental predictions** | `gpr_predictions` | Gaussian Process Regression forecasts for held-out period (chronological split: first 75% train, last 25% test) |
| **Baseline predictions** | `persistence_predictions` | Simple persistence (repeat last training value) — outperforms GPR on all parcels |
| **Verification verdicts** | `data/verification/*.json` | Rule-based vegetation classification, NOT compliance verdict |

### 4. How to Describe GPR vs Persistence

**Required disclaimer on every chart/page:**
> "This is an experimental NDVI trajectory prediction. Persistence (repeating the last observed value) outperformed the Gaussian Process on all four parcels. The shaded band is the model's nominal 95% predictive interval — it is uncalibrated and observed coverage on a small test set does not prove calibration. This does NOT verify agricultural compliance or authorize settlement."

**Key metrics from corrected evaluation (Day 6C.2B):**
| Parcel | GPR MAE | Persistence MAE | GPR better? |
|--------|---------|-----------------|-------------|
| parcel_01 | 0.217 | 0.032 | No |
| parcel_02 | 0.102 | 0.018 | No |
| parcel_03 | 0.096 | 0.031 | No |
| parcel_04 | 0.110 | 0.038 | No |

### 5. Missing Files / Integration Blockers

**None.** All required assets exist and are tracked in Git:
- ✅ Four trajectory PNG charts
- ✅ `data/ml/ai_insights.json` (valid JSON, matches corrected evaluation)
- ✅ Four verification JSON reports
- ✅ Four real NDVI+quality CSVs
- ✅ Four parcel GeoJSON files

**Note:** The original Day 6C.2 (buggy) outputs in `data/ml/trajectory_evaluation.json` and `data/ml/trajectory_test_predictions.csv` are preserved but **must not be used** for display. The corrected versions are in `data/ml/evaluation_corrected/` and `data/ml/ai_insights.json`.

---

## For Dorian (Smart Contracts / EIP-712)

### 1. Existing Verdict Codes (Immutable)

| JSON | Solidity / EIP-712 | Meaning |
|------|-------------------|---------|
| `conform` | 0 | Observations meet the configured policy |
| `nonconform` | 1 | Sufficient observations, policy condition not met |
| `inconclusive` | 2 | Insufficient evidence; does NOT mean the practice failed |

**These are the single source of truth.** Do not change.

### 2. Vegetation Assessment ≠ Settlement Authorization

| Concept | Description |
|---------|-------------|
| **Vegetation verdict** (`verdict`) | Experimental NDVI classification result from satellite data only. Indicates vegetation presence above threshold during the commitment window. |
| **Evidence sufficiency** (`evidence_quality`) | `"assessed"` = real `valid_pixel_fraction` data available; `"unknown"` = no quality metadata. When `"unknown"`, result is explicitly flagged as experimental and non-settlement-ready. |
| **Settlement authorization** | **NOT produced by this verifier.** Requires: (1) authorized verifier review, (2) EIP-712 signature by verifier, (3) backend receipt verification, (4) escrow contract `settle()` call. The ML/verification module only produces evidence. |

### 3. Canonical Hashing Ownership

| Hash | Owner | Algorithm | Input |
|------|-------|-----------|-------|
| `plan_hash` | Corina (backend) | SHA-256 | Canonical plan snapshot bytes (no floats, sorted keys, compact) |
| `evidence_hash` | Corina (backend) | SHA-256 | Canonical evidence document bytes |
| `commitment_id` | Corina + Dorian | Keccak-256 | `abi.encode(parcelIdBytes32, seasonIdBytes32)` via `eth_abi` |

**Unresolved compatibility issue:** `backend/hashing.py::compute_commitment_id()` depends on `eth_abi` + `web3`. These are now installed in `.venv` and declared as required backend dependencies. The test `tests/test_hashing.py::test_compute_commitment_id` passes with the fixture values:
- `parcel_id_bytes32`: `0x1111...1111` (64 hex)
- `season_id_bytes32`: `0x2222...2222` (64 hex)
- Expected `commitment_id`: `0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871`

**Action for Dorian:** Confirm the same `commitment_id` is computed in Foundry/ethers test using the same two `bytes32` inputs. The Python function uses `Web3().keccak(encode(["bytes32","bytes32"], [p_bytes, s_bytes]))`.

### 4. EIP-712 Domain (Fixed)

```javascript
const domain = {
  name: "TerraCycleEscrow",
  version: "1",
  chainId: <actual_chain_id>,      // e.g., 31337 (Anvil) or 11155111 (Sepolia)
  verifyingContract: <contract_address>,
};
const types = {
  VerificationResult: [
    { name: "commitmentId", type: "bytes32" },
    { name: "planHash", type: "bytes32" },
    { name: "evidenceHash", type: "bytes32" },
    { name: "verdict", type: "uint8" },      // 0, 1, 2
    { name: "validUntil", type: "uint64" },  // Unix seconds
  ],
};
```

---

## Final Test Results

```text
335 passed, 40 warnings in 11.60s
```

**Breakdown:**
- `test_hashing.py`: 5 passed (includes `test_compute_commitment_id` — eth_abi issue resolved)
- `test_ml_insights.py`: 16 passed
- All other test modules: passing

### Verification Reproduction (All 4 Parcels)

| Parcel | Verdict | Code | Valid Obs | Vegetated | Vegetated % | Temporal Coverage |
|--------|---------|------|-----------|-----------|-------------|-------------------|
| parcel_01 | nonconform | 1 | 29/48 | 10 | 34% | 0.76 |
| parcel_02 | nonconform | 1 | 63/97 | 30 | 48% | 1.00 |
| parcel_03 | nonconform | 1 | 62/97 | 31 | 50% | 0.92 |
| parcel_04 | nonconform | 1 | 60/97 | 23 | 38% | 0.92 |

All reports have `evidence_quality: "assessed"` (real `valid_pixel_fraction` data present).

---

## Files Changed in This Branch

| File | Change |
|------|--------|
| `backend/requirements.txt` | **Added** `eth_abi>=6.0.0` and `web3>=8.0.0` for hashing tests |
| `docs/day7-integration-checklist.md` | **Created** (this document) |

**No other files modified.** All satellite data, ML outputs, and verification reports were already present and tracked in Git.

---

## Day 7A Completion Status

| Checkpoint | Status |
|------------|--------|
| eth_abi / web3 dependency resolved | ✅ Done — added to `backend/requirements.txt`, tests pass |
| Full pytest suite (including hashing) | ✅ 335 passed |
| All 4 real NDVI+quality CSVs exist | ✅ Verified |
| All 4 JSON verification reports readable | ✅ Verified |
| Verification outputs reproducible | ✅ `scripts/run_verification.py --all` matches |
| Verdict mapping conform=0, nonconform=1, inconclusive=2 | ✅ Confirmed |
| Inconclusive ≠ settlement authorization | ✅ Enforced in code & docs |
| Commitment window respected (inclusive start, exclusive end) | ✅ Verified |
| No cross-parcel data attribution | ✅ Verified |
| No new satellite extraction needed | ✅ All data offline |
| 4 ML charts exist | ✅ `data/ml/plots/parcel_0{1-4}_trajectory.png` |
| AI Insights JSON valid & matches corrected evaluation | ✅ `data/ml/ai_insights.json` |
| Persistence outperforms GPR explicitly stated | ✅ In JSON, charts, docs |
| GPR uncertainty limitations stated | ✅ "nominal, uncalibrated" in JSON & charts |
| ML not presented as organic certification proof | ✅ Disclaimers in all outputs |
| ML experiment separate from compliance verification | ✅ Separate API, separate outputs |
| Git-tracked files available to teammates | ✅ All required files in `data/` tracked |
| No large raw data dumps / secrets committed | ✅ `.gitignore` respected |
| Integration handoff document created | ✅ This file |

**Day 7A: COMPLETE**

---

## Next Steps (Not Part of Day 7A)

- Corina: Integrate `verify_parcel()` into `POST /commitments/{id}/verify` endpoint
- Corina: Add `eth_abi` and `web3` to backend deployment requirements
- Oana: Consume `data/ml/ai_insights.json` and PNG charts in Verification/Passport pages
- Dorian: Verify `compute_commitment_id()` matches Solidity/Foundry output
- All: Run fresh clone verification using `SETUP.md` (when available)