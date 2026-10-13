# TerraCycle Proof: API contract

Status: **proposal, v0.1 (13 Oct 2026).** The endpoints below are agreed interface
proposals. Nothing here is implemented yet except `GET /health`.
Changing an interface requires a PR that also updates the examples and the shared fixtures.

Owner: backend (Corina). Reviewers: frontend (Oana), signing (Dorian), ML (Crenguța).

## 1. Conventions

- Base path: `/api/v1`. Content type: `application/json; charset=utf-8`.
- Hashes and bytes32 values: `0x` + 64 lowercase hex characters.
- Addresses: `0x` + 40 hex characters.
- Wei amounts travel as **decimal strings** (never JSON numbers), and become `BigInt` in ethers.
- Dates are ISO 8601 (`2024-04-15`). EVM times are Unix seconds.
- Verdict mapping (single source of truth, same in JSON and Solidity):
  `conform` → 0, `nonconform` → 1, `inconclusive` → 2.
- `plan_id` (database/API id) is **different** from `commitment_id` (on-chain id).
- `commitment_id = keccak256(abi.encode(parcelId, seasonId))`, computed by the backend and checked against Dorian's fixture.
- Snapshot endpoints return the **exact stored bytes**. Clients must hash those bytes with SHA-256 without `JSON.parse` followed by re-serialization.
- A technical failure (model error, signer timeout) is an **error response**. It is never turned into a `nonconform` verdict.

### Error format

Every error has the same shape. The frontend displays messages based on `code`, not on `message`.

```json
{
  "error": {
    "code": "PLAN_HASH_MISMATCH",
    "message": "The document does not match the registered commitment."
  }
}
```

| HTTP | `code` | When | Status |
|---|---|---|---|
| 503 | `DB_UNAVAILABLE` | Database not reachable | implemented |
| 422 | `VALIDATION_ERROR` | Request body fails validation | proposed |
| 404 | `PARCEL_NOT_FOUND` / `PLAN_NOT_FOUND` / `COMMITMENT_NOT_FOUND` | Unknown id | proposed |
| 409 | `COMMITMENT_ALREADY_EXISTS` | Second commitment for the same parcel and season | proposed |
| 409 | `PLAN_HASH_MISMATCH` | Stored document no longer matches the registered hash | proposed |
| 422 | `TX_VERIFICATION_FAILED` | On-chain check failed (network, contract, id, hash, actors or amount) | proposed |
| 502 | `SIGNING_FAILED` | Node signer failed or timed out | proposed |
| 502 | `INFERENCE_FAILED` | ML module raised a technical error | proposed |

## 2. Endpoints

| Method | Path | Purpose | Status |
|---|---|---|---|
| GET | `/health` | API and database are up | implemented |
| GET | `/config` | Public config: network, contract, ABI version, verifier, app URL | proposed |
| GET | `/config/abi` | Contract ABI | proposed |
| GET | `/parcels` | Fixed parcel catalog | proposed |
| POST | `/plans` | Takes crop history, returns rotation variants | proposed |
| GET | `/plans/{plan_id}/snapshot` | Exact bytes of the anchored plan document | proposed |
| POST | `/commitments/prepare` | Chooses a rotation, freezes the document, returns the hash | proposed |
| POST | `/commitments/{id}/transactions` | Backend verifies an on-chain transaction | proposed |
| GET | `/commitments/{id}` | State, transactions, verdict | proposed |
| POST | `/commitments/{id}/verify` | Integrity check, inference, evidence, signature | proposed |
| GET | `/evidence/{evidence_id}/snapshot` | Exact bytes of the signed evidence | proposed |
| GET | `/passports/{id}` | Data for the `/passport/{commitment_id}` page | proposed |

## 3. Examples

All values are illustrative fixtures. The shared end-to-end fixture must keep the same
parcel, ids, plan, policy and expected results for every team member.

### GET /health

```json
{ "status": "ok", "database": "ok" }
```

### GET /config

```json
{
  "chain_id": 11155111,
  "network_name": "sepolia",
  "contract_address": "0x1234567890abcdef1234567890abcdef12345678",
  "abi_url": "/api/v1/config/abi",
  "abi_version": "2026-10-22-v1",
  "verifier_address": "0x9876543210fedcba9876543210fedcba98765432",
  "app_url": "https://terracycle-demo.example.com"
}
```

The frontend reads the network and ABI from here and forces MetaMask to this `chain_id`.

### POST /plans

Request:

```json
{
  "parcel_id": "RO-DJ-001",
  "season_id": "2024",
  "crop_history": [
    { "year": 2022, "crop_id": "wheat" },
    { "year": 2023, "crop_id": "maize" }
  ],
  "treatments": [],
  "requested_crop_id": "peas"
}
```

Response `200`:

```json
{
  "plan_id": "plan-demo-001",
  "parcel_id": "RO-DJ-001",
  "season_id": "2024",
  "rotations": [
    {
      "rotation_id": "rotation-01",
      "crops": [
        { "year": 2025, "crop_id": "peas" },
        { "year": 2026, "crop_id": "wheat" },
        { "year": 2027, "crop_id": "maize" }
      ],
      "score": 0.82,
      "explanations": [
        "Peas fix nitrogen, recommended after a cereal",
        "Wheat after a legume: residual nitrogen available"
      ],
      "risks": ["Spring drought 2025: irrigation recommended"]
    },
    {
      "rotation_id": "rotation-02",
      "crops": [
        { "year": 2025, "crop_id": "sunflower" },
        { "year": 2026, "crop_id": "wheat" },
        { "year": 2027, "crop_id": "maize" }
      ],
      "score": 0.68,
      "explanations": ["Sunflower needs rich soil; drought risk"],
      "risks": ["High water consumption"]
    }
  ]
}
```

The final document of each variant includes the submitted history, the treatments, the chosen rotation and the verification policy.

### POST /commitments/prepare

Request:

```json
{
  "plan_id": "plan-demo-001",
  "rotation_id": "rotation-02",
  "beneficiary_address": "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
  "verification_policy_id": "vegetation-proxy-v1"
}
```

Response `200`:

```json
{
  "commitment_id": "0x1111111111111111111111111111111111111111111111111111111111111111",
  "plan_hash": "0x3333333333333333333333333333333333333333333333333333333333333333",
  "parcel_id": "RO-DJ-001",
  "season_id": "2024",
  "beneficiary_address": "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
  "settle_deadline": "1792800000",
  "snapshot_url": "/api/v1/plans/plan-demo-001/snapshot",
  "state": "prepared"
}
```

`settle_deadline` must be computed for the real demo time. Satellite observations may be
from 2024, but escrow deadlines must be in the future when the demo runs.

### POST /commitments/{id}/transactions

Request (sent after MetaMask confirms):

```json
{
  "tx_hash": "0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
  "tx_type": "register_commitment",
  "actor": "farmer"
}
```

Response `200`:

```json
{
  "commitment_id": "0x1111111111111111111111111111111111111111111111111111111111111111",
  "tx_hash": "0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
  "tx_type": "register_commitment",
  "status": "confirmed",
  "block_number": 12345678,
  "checks_passed": [
    "network_matches",
    "contract_matches",
    "commitment_id_matches",
    "plan_hash_matches",
    "actors_match",
    "amount_matches"
  ]
}
```

A hash received from the browser is not proof of success. The backend compares the
transaction with the expected commitment before confirming. The UI shows "paid" only after this confirmation.

### POST /commitments/{id}/verify

No request body. Response `200`:

```json
{
  "commitment_id": "0x1111111111111111111111111111111111111111111111111111111111111111",
  "evidence_id": "evidence-demo-001",
  "evidence_hash": "0x2222222222222222222222222222222222222222222222222222222222222222",
  "verdict": "conform",
  "verdict_code": 0,
  "attestation": {
    "commitmentId": "0x1111111111111111111111111111111111111111111111111111111111111111",
    "planHash": "0x3333333333333333333333333333333333333333333333333333333333333333",
    "evidenceHash": "0x2222222222222222222222222222222222222222222222222222222222222222",
    "verdict": 0,
    "validUntil": 1792800000
  },
  "signature": "0x4444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444",
  "reason_codes": [],
  "snapshot_url": "/api/v1/evidence/evidence-demo-001/snapshot"
}
```

The `attestation` object is passed unchanged from the API to ethers to the contract's
`settle()`. If it has to be modified at any step, there is an encoding mismatch.

For a verdict that is not conclusive, `verdict` is `"inconclusive"`, `verdict_code` is `2`, and
`reason_codes` explains why, for example `["INSUFFICIENT_VALID_OBSERVATIONS"]`.

## 4. Open items

| Item | With | Impact |
|---|---|---|
| Final parcel id format and season (`RO-DJ-001`, `2024` are examples) | Crenguța | All ids |
| Source of `reward_wei` (not yet in the prepare response) | Dorian | `commitments.reward_wei` |
| Exact `tx_type` values (proposal: `register_commitment`, `fund_commitment`, `settle`, `refund`) | Dorian | `POST /transactions` validation |
| `GET /commitments/{id}` and `GET /passports/{id}` response shapes | Oana | Not specified in the guide; draft after the wireframes |
| `settle_deadline` is a string here but `validUntil` is a number in the attestation | Dorian | Keep as is unless the contract fixture says otherwise |
| Canonicalization rules: null vs absent, number format, list order, Unicode | Corina + Dorian | Hash stability |
