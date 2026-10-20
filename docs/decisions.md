# Decisions — TerraCycle Proof

Status: **working draft, 19 oct 2026.** This document records decisions that are already implemented or agreed. It is updated when a decision changes.

## 1. Hashing and canonicalization

- **Algorithm:** `SHA-256` over canonical UTF-8 JSON bytes.
- **Canonical form:** `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`.
- **Floats are forbidden** in snapshots — fixed-precision ints or strings only.
- **Snapshot includes:** parcel_id, season_id, plan_id, rotation_id, crop_history, treatments, requested_crop_id, selected_rotation, beneficiary_address, verification_policy_id, rules_version, snapshot_version.
- **Persisted together:** `plan_snapshot` (bytes) + `plan_hash` (hex) in the same DB transaction.
- **Commitment ID:** `keccak256(abi.encode(bytes32, bytes32))` computed in Python via `eth_abi` + `web3`, matching Solidity output.

## 2. IDs

- `plan_id` = deterministic `plan-` + 12-char SHA-256 of canonical request. Same input → same plan (idempotent).
- `commitment_id` = EVM `keccak256` of `(parcelIdBytes32, seasonIdBytes32)`. Never derived from plan_id.
- `parcel_id_bytes32` / `season_id_bytes32` come from `data/fixtures/demo.json` — single source of truth.

## 3. Rotations

- **Scoring:** deterministic rule-based. Start at 100, −35 for same crop in consecutive years, −10 for same crop family, +0 otherwise.
- **Crop families:** cereal (wheat, maize, barley), legume (peas, soybean, alfalfa), asteraceae (sunflower), brassicaceae (rapeseed).
- **Selection:** top 2 sequences by score, normalized to 0–1 against the best.
- **Explanations:** generated from the same rule, not an external agronomic API.

## 4. Climate data

- **Provider:** Open-Meteo ERA5-Land via `https://archive-api.open-meteo.com/v1/archive`.
- **Cache:** `data/climate/{parcel_id}_{season_id}.json` — never fetched twice in the same session.
- **Coordinates:** stored in `data/fixtures/demo.json` (Dolj ~44.33,23.79 / Ialomița ~44.54,26.27 / Brașov ~45.66,25.59).
- **Fallback:** if Open-Meteo is unreachable, return `fixture_fallback` with null summary — never crash.
- **Purpose:** informational context for ML; not a scoring input for the NDVI verdict.

## 5. Passport

- **Visibility:** public, no auth.
- **Data shape:** defined in `data/fixtures/api_examples.json` → `get_passports`.
- **Limitations:** always included — NDVI proxy ≠ eco-certification, retrospective demo, not a live guarantee.

## 6. Error format

Every error follows:
```json
{ "error": { "code": "STABLE_CODE", "message": "Human-readable message." } }
```
Codes are stable for frontend logic; messages may change.

## 7. Pending decisions

| Item | Owner | Impact |
|---|---|---|
| `reward_wei` source | Dorian | `/prepare` response |
| Exact `tx_type` values | Dorian | `/transactions` validation |
| `GET /commitments/{id}` and `/passports/{id}` final shapes | Oana | Frontend types |
| Canonicalization edge cases (null vs absent, Unicode) | Corina + Dorian | Hash stability |
