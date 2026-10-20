# Evidence Builder Handoff — Task 7B.1

**Branch:** `feat/gpr-chronological-evaluation`
**Created:** 2026-10-20
**Status:** Complete — all 489 tests passing

---

## 1. Adapter Function Signature

```python
from backend.services.evidence_builder import (
    build_evidence_document,
    build_attestation,
    verify_evidence_document,
)

evidence_doc, evidence_bytes, evidence_hash = build_evidence_document(
    verifier_result=dict,      # Output from verify_parcel()
    commitment=Commitment,     # SQLAlchemy Commitment model instance
    policy=dict,               # Verification policy from fixture
)

attestation = build_attestation(
    commitment=Commitment,
    evidence_hash=str,         # 0x-prefixed SHA-256
    verdict_code=int,          # 0, 1, or 2
)

is_valid = verify_evidence_document(evidence_doc)  # Returns True or raises ValueError
```

---

## 2. Required Inputs

| Input | Source | Required Fields |
|-------|--------|-----------------|
| `verifier_result` | `backend.ml.rules.verify_parcel()` | `verdict`, `verdict_code`, `reason_code`, `observations`, `quality`, `model`, `source` |
| `commitment` | SQLAlchemy `Commitment` model | `commitment_id`, `plan_hash`, `parcel_id`, `season_id`, `verification_policy_id`, `settle_deadline` |
| `policy` | `data/fixtures/demo.json` → `verification_policies[policy_id]` | `policy_version`, `type`, `window_start`, `window_end`, `min_observations`, `min_valid_pixel_fraction`, `min_temporal_coverage`, `required_fraction`, `ndvi_threshold` |

---

## 3. Field Mapping — Verifier → Canonical Evidence

| Canonical Field | Verifier Source | Conversion |
|-----------------|-----------------|------------|
| `schema_version` | — | Constant `"evidence-v1"` |
| `commitment_id` | `commitment.commitment_id` | Direct |
| `plan_hash` | `commitment.plan_hash` | Direct |
| `parcel_id` | `commitment.parcel_id` | Direct |
| `season_id` | `commitment.season_id` | Direct |
| `policy.policy_version` | `policy["policy_version"]` | Direct |
| `policy.type` | `policy["type"]` | Direct |
| `policy.window_start` | `policy["window_start"]` | Append `T00:00:00Z` if date-only |
| `policy.window_end` | `policy["window_end"]` | Append `T00:00:00Z` if date-only |
| `policy.minimum_observations` | `policy["min_observations"]` | Direct |
| `policy.minimum_valid_pixel_percent` | `policy["min_valid_pixel_fraction"]` | `int(round(v * 100))` |
| `policy.minimum_temporal_coverage_percent` | `policy["min_temporal_coverage"]` | `int(round(v * 100))` |
| `policy.minimum_positive_percent` | `policy["required_fraction"]` | `int(round(v * 100))` |
| `observations[*].acquired_at` | `obs["acquired_at"]` | Direct |
| `observations[*].scene_id` | `obs.get("scene_id")` | `null` (not in openEO export) |
| `observations[*].ndvi_milli` | `obs["ndvi_mean"]` | `int(round(ndvi_mean * 1000))` |
| `observations[*].valid_pixel_percent` | `obs.get("valid_pixel_fraction")` | `int(round(vpf * 100))` or `null` |
| `observations[*].is_valid` | `obs["is_valid_observation"]` | Direct |
| `observations[*].vegetation_class` | Derived | `1 if (is_valid and ndvi_mean > ndvi_threshold) else 0` |
| `quality.total_rows` | `quality["total_rows"]` | Direct |
| `quality.valid_count` | `quality["valid_count"]` | Direct |
| `quality.excluded_count` | `quality["excluded_count"]` | Direct |
| `quality.temporal_coverage_percent` | `quality["temporal_coverage"]` | `int(round(tc * 100))` or `null` |
| `quality.covered_intervals` | `quality["covered_intervals"]` | Direct |
| `quality.total_intervals` | `quality["total_intervals"]` | Direct |
| `quality.inconclusive_reason` | `quality["inconclusive_reason"]` | Direct |
| `dataset.provider` | `source["provider"]` | Direct |
| `dataset.dataset` | `source["dataset"]` | Direct |
| `dataset.source_file` | `Path(source["csv_file"]).name` | Basename only |
| `dataset.method` | `source["method"]` | Direct |
| `model.model_version` | `model["model_version"]` | Direct |
| `model.source` | `model["source"]` | Direct |
| `verdict` | `verifier_result["verdict"]` | Direct |
| `verdict_code` | `verifier_result["verdict_code"]` | Direct |

---

## 4. Exact Numeric Conversion Rules

| Conversion | Formula | Rounding | Notes |
|------------|---------|----------|-------|
| `ndvi_milli` | `round(ndvi_mean * 1000)` | Banker's rounding (Python `round`) | 0.444298 → 444, 0.853875 → 854 |
| `valid_pixel_percent` | `round(vpf * 100)` | Banker's rounding | 1.0 → 100, 0.9046 → 90, 0.0956 → 10 |
| `temporal_coverage_percent` | `round(tc * 100)` | Banker's rounding | 0.76 → 76 |
| `minimum_valid_pixel_percent` | `int(round(min_valid_pixel_fraction * 100))` | Exact | 0.50 → 50 |
| `minimum_temporal_coverage_percent` | `int(round(min_temporal_coverage * 100))` | Exact | 0.50 → 50 |
| `minimum_positive_percent` | `int(round(required_fraction * 100))` | Exact | 0.80 → 80 |

**Vegetation class derivation:**
```
vegetation_class = 1 if (is_valid_observation and ndvi_mean > ndvi_threshold) else 0
```
- Invalid observations (`is_valid_observation == False`) always get `vegetation_class = 0`
- Valid observations with NDVI ≤ threshold get `0`
- Valid observations with NDVI > threshold get `1`

**Scene ID:** Always `null` (not exposed by openEO aggregated export)

**Missing `valid_pixel_fraction`:** Becomes `null` in canonical output

---

## 5. Example Invocation

```python
from backend.ml.rules import verify_parcel
from backend.services.evidence_builder import build_evidence_document, build_attestation
from backend.models import Commitment
from backend.db import get_db

# In FastAPI endpoint:
def verify_commitment(commitment_id: str, db: Session = Depends(get_db)):
    commitment = db.get(Commitment, commitment_id)
    
    # Load policy from fixture
    policy = load_policy(commitment.verification_policy_id)
    
    # Call scientific verifier
    verifier_result = verify_parcel(
        parcel_id=commitment.parcel_id,
        policy=policy,
        evidence_directory="data/ndvi",
    )
    
    # Build canonical evidence document
    evidence_doc, evidence_bytes, evidence_hash = build_evidence_document(
        verifier_result=verifier_result,
        commitment=commitment,
        policy=policy,
    )
    
    # Validate
    verify_evidence_document(evidence_doc)
    
    # Build EIP-712 attestation
    attestation = build_attestation(commitment, evidence_hash, evidence_doc["verdict_code"])
    
    # Sign via Node signer
    signature = sign_attestation(attestation)
    
    # Persist Verdict
    verdict = Verdict(
        evidence_id=evidence_doc["evidence_id"],
        commitment_id=commitment.commitment_id,
        evidence_hash=evidence_hash,
        evidence_snapshot=evidence_bytes,
        verdict=evidence_doc["verdict"],
        verdict_code=evidence_doc["verdict_code"],
        reason_codes=[verifier_result["reason_code"]],
        attestation=attestation,
        signature=signature,
        valid_until=commitment.settle_deadline,
        model_version=evidence_doc["model"]["model_version"],
        policy_version=commitment.verification_policy_id,
    )
    db.add(verdict)
    db.commit()
```

---

## 6. Canonical Serialization & Hashing Steps

```python
from backend.hashing import hash_snapshot

# 1. Build evidence document (must contain NO floats)
evidence_doc = {...}  # All ints, strings, bools, null, dict, list

# 2. Canonicalize and hash in one step
evidence_bytes, evidence_hash = hash_snapshot(evidence_doc)
# evidence_bytes: raw canonical UTF-8 bytes
# evidence_hash: "0x" + 64 hex chars (SHA-256)

# 3. Store evidence_bytes in Verdict.evidence_snapshot
# 4. evidence_hash goes into attestation.evidenceHash
```

**Critical:** `hash_snapshot()` internally calls `canonical_bytes()` which **rejects any float** at any nesting level. The evidence builder ensures all numeric values are converted to integers before hashing.

---

## 7. Required Error Handling

| Error Condition | Exception | HTTP Code (if in endpoint) |
|-----------------|-----------|----------------------------|
| Missing `commitment_id` or `plan_hash` | `ValueError` | 500 / 422 |
| Missing `parcel_id` or `season_id` | `ValueError` | 500 / 422 |
| Missing verifier keys | `ValueError` | 502 (INFERENCE_FAILED) |
| Invalid verdict | `ValueError` | 502 (INFERENCE_FAILED) |
| NDVI out of range [-1, 1] | `ValueError` | 500 |
| VP fraction out of range [0, 1] | `ValueError` | 500 |
| Float in canonical evidence | `TypeError` from `canonical_bytes()` | 500 |
| Missing `scene_id` | Handled (becomes `null`) | — |
| Missing `valid_pixel_fraction` | Handled (becomes `null`) | — |

---

## 8. Unresolved Integration Decisions

| Decision | Status | Decider |
|----------|--------|---------|
| Node signer payload = attestation dict | ✅ Confirmed | Corina + Dorian |
| `validUntil` = `commitment.settle_deadline` (Unix seconds) | ✅ Confirmed | Corina |
| Evidence ID format: `evidence-{parcel_id}-{season_id}` | ✅ Used in verify.py | Corina |
| `reason_code` placement: only in Verdict/attestation, not evidence doc | ✅ Per canonical schema | Corina |
| Rounding convention: Python `round()` (banker's) | ✅ Implemented | Crenguța + Corina |

---

## 9. Test Results

```
489 tests passed (including 43 new evidence_builder tests)
0 failed, 0 skipped
```

**Key validations passing:**
- ✅ Real verifier output → canonical evidence document
- ✅ All 4 parcels produce valid evidence documents
- ✅ Canonical serialization accepts built documents (no floats)
- ✅ Deterministic serialization (same input → same hash)
- ✅ Hash changes when evidence changes
- ✅ Canonical fixture passes validation
- ✅ Built document matches fixture structure
- ✅ Missing `scene_id` → `null`
- ✅ Missing `valid_pixel_fraction` → `null`
- ✅ Original verifier data not mutated
- ✅ Verdict and verdict_code preserved
- ✅ Invalid evidence documents rejected

---

## 10. Files Created

| File | Purpose |
|------|---------|
| `backend/services/evidence_builder.py` | Core adapter implementation |
| `backend/services/__init__.py` | Package init |
| `tests/test_evidence_builder.py` | 43 focused validation tests |

---

## 11. Task 7B.1 Status: COMPLETE ✅

The evidence builder adapter is implemented, tested, and ready for integration into the FastAPI verification endpoint (Task 7B.2).

**No changes made to:**
- `verify_parcel()` scientific verifier
- Canonical hashing (`backend/hashing.py`)
- Satellite data or ML models
- Solidity contracts or Node signer

**All 489 tests pass.**