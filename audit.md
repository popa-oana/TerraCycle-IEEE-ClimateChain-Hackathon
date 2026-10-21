# Audit Progress Log

## Overview

The TerraCycle MVP now runs **end to end on real data**, from Sentinel-2 pixels to an on-chain
record, and both demo surfaces display it.

```text
data/ndvi/parcel_01_2024_quality.csv   (real Sentinel-2 L2A export, Copernicus Data Space)
        │  backend/ml/rules.py            policy cover-v1, window 2024-03-01 .. 2024-11-01
        ▼
  verdict  nonconform (code 1)   "10/29 observations above NDVI threshold 0.35 (fraction=0.34, required=0.8)"
        │  backend/api/v1/{plans,commitments}.py   real plan -> real commitment_id + plan_hash
        ▼  backend/services/evidence_builder.py + backend/hashing.py   5685 canonical bytes
  evidence hash  0x281cf44e592ed2e57dd40f16f70c63f96a281ec8fd249b85ce1a96a5cab0dd75
        │  contracts/smoke_test_real_evidence.py   local Anvil, chain id 31337
        ▼
  TerraCycleEvidenceRegistry   tx 0x78187395…d86a7, receipt status 1, read-back MATCH
        │  contracts/smoke_test_real_evidence.py --output
        ▼
  data/demo/latest_proof.json   (written atomically, only after all integrity checks pass)
        ├──► demo/index.html                    read-only dashboard        :8090
        └──► frontend/  Step 05 Verification    React 19 / Vite 8          :5173
```

**Two demo surfaces, both read-only.** Neither triggers a blockchain transaction, and neither shows
a value that was not produced by a real run.

* `demo/index.html` — standalone page, no framework, no build step.
* `frontend/` — Oana's recovered React app (found on `origin/main`, restored in TASK-003D.1); Step 05
  "Verification" renders the same document through a typed, runtime-validating client.

### Completed work

| Task | Result |
|---|---|
| TASK-001 | `_load_bytes32_map()` merges the authoritative `reference_parcel` identifiers instead of dropping them; conflicting identifiers raise `FIXTURE_CONFLICT` |
| TASK-001B | The float rotation `score` is excluded from the canonical plan snapshot at the snapshot-construction boundary; the `/plans` -> `/commitments/prepare` workflow works |
| TASK-002A | `TerraCycleEvidenceRegistry.sol` — append-only evidence registry, verifier-only writer, 15 Foundry tests |
| TASK-002B | Deployed to local Anvil, one real transaction, event emitted, record read back |
| TASK-002C | The real satellite result of `parcel_01` recorded on chain; read-back matched exactly |
| TASK-003A | `data/demo/latest_proof.json` — atomic, integrity-checked summary; a failed run removes the stale document |
| TASK-003B | Read-only demo page + `scripts/serve_demo.py` (stdlib only, 4 routes, no repository exposure) |
| TASK-003D.1 | Oana's frontend recovered from `origin/main` — 27 files, byte-identical, builds clean |
| TASK-003D.2 | React Step 05 Verification page over the real proof document |

Current test state: **597 Python tests passed, 15 Solidity tests passed**, TypeScript, ESLint and the
Vite production build clean, and the page verified in headless Chrome (every JSON value rendered, no
console errors, no fabricated data when the proof server is down).

### Honest limits

- The scientific verdict is **nonconform**, not conform. A successful transaction says the evidence
  hash was recorded; it says nothing about the outcome of the verification.
- The chain is **local Anvil** (chain id 31337). These transactions are not public testnet proof
  and disappear with the chain.
- The registry stores evidence **metadata** only — no escrow, no EIP-712 signing, no settlement, no
  payment, and it does not verify satellite observations or organic compliance.
- `origin/main` is **ahead** of this branch: it still contains both TASK-001/001B backend defects,
  and it adds 44 files (evidence/passports/transactions/climate endpoints, `chain_service.py`, the
  Node signer, the escrow contract, 3 test files).

### Open items

1. **TASK-003D.3 — Parcel API compatibility.** `frontend/src/lib/types.ts` requires
   `latitude`/`longitude`; this branch's parcel records have none, so step 01 still fails with
   `INVALID_RESPONSE`. `data/fixtures/demo.json` was deliberately not touched.
2. **Environment.** Node 22.11 is below Vite 8's `>=22.12`, so the optional
   `@rolldown/binding-win32-x64-msvc` must be installed into `node_modules` (no manifest change);
   `uvicorn` is missing from the venv, so the FastAPI backend cannot be started locally.

### Running the demo

```bash
python scripts/serve_demo.py                 # proof server, http://127.0.0.1:8090
cd frontend && npm run dev                   # React app, http://127.0.0.1:5173/#verification
```

### TASK-003D.2 — React Verification Page
- Status: COMPLETE
- Changed: `frontend/src/{lib/proof.ts,lib/types.ts,lib/api.ts,components/StepProgress.tsx,pages/ProofPage.tsx,App.tsx}`, `frontend/{vite.config.ts,.env.example}`, `tests/test_frontend_proof_contract.py` (new), `audit.md`
- Done: Added a typed, validating proof client and a Step 05 page showing the real verdict, canonical evidence and local-Anvil record. Step 05 opens directly via `#verification` or the rail; steps 01–04 are not required.
- TypeScript: PASS
- ESLint: PASS
- Build: PASS
- Browser: PASS (headless Chrome: all values rendered, no console errors, no fabricated data on failure)
- Real proof: DISPLAYED
- Existing demo: PRESERVED (9/9 checksums; pytest 597, forge 15)
- Remaining: Step 01 still needs `latitude`/`longitude` in the parcel payload
- Next: TASK-003D.3 — Parcel API Compatibility
