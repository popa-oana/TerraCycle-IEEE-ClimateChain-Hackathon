# Audit Progress Log

### TASK-002A — Minimal Solidity Evidence Registry
- Status: COMPLETE
- Changed: `contracts/` (contract, tests, foundry config/lock, ABI, README), `.gitmodules`, `audit.md`
- Done: Added an append-only registry storing one evidence hash + verdict per commitment id, writable only by the constructor-configured verifier. The pre-existing `TerraCycleEscrow.sol` on `origin/main` was found and left untouched.
- Tests: `forge build` OK; `forge test -vv` → 15 passed, 0 failed.
- Limitations: No ETH/escrow, no EIP-712, no settlement, no satellite verification, no verifier rotation.
- Remaining: None
- Next: TASK-002B — Local deployment and genuine evidence transaction

### TASK-002B — Local Blockchain Transaction
- Status: COMPLETE
- Changed: `contracts/smoke_test.py` (new), `contracts/README.md`, `tests/test_evidence_registry_smoke_script.py` (new), `audit.md`
- Done: Deployed the registry to local Anvil and ran one real evidence transaction with synthetic TEST values; added a Web3 smoke test that deploys, records, checks the receipt/event and reads the record back, exiting non-zero on failure.
- Tests: `forge build` OK; `forge test -vv` → 15 passed, 0 failed. Smoke test → 21 checks, exit 0 (exit 1 verified on failure). Python → 537 passed.
- Chain: local Anvil, chain id 31337 (127.0.0.1:8545); no real ETH, no public network
- Deployment: `0x5FbDB2315678afecb367f032d93F642f64180aa3`, tx `0x402058dffc02a27eaa4d40f600cfbb526213f648baadaa7a576c7444ce27a494`, status 0x1
- Transaction: `0xb12c70b050beed7de5a7fb14b6d53141b5960ee397f63ac29b653f5293a0135a`, status 0x1, 1 event, read-back matches exactly
- Remaining: None
- Next: TASK-002C — Real Satellite Evidence Hash Integration

### TASK-002C — Real Satellite Evidence on Blockchain
- Status: COMPLETE
- Changed: `contracts/smoke_test.py` (refactored into reusable helpers), `contracts/smoke_test_real_evidence.py` (new), `tests/test_real_evidence_blockchain.py` (new), `contracts/README.md`, `audit.md`
- Done: Generated genuine evidence for `parcel_01` with the existing verifier, canonical evidence builder and hashing, then recorded it on local Anvil; reused the existing preparation flow for the commitment metadata.
- Tests: new focused tests 13 passed (1 skipped without Anvil); evidence builder + hashing 48 passed; full Python 550 passed; `forge test -vv` 15 passed, 0 failed; real-evidence smoke test exit 0.
- Parcel: `parcel_01` / `season-2024`, policy `cover-v1`, `parcel_01_2024_quality.csv`
- Evidence hash: `0x281cf44e592ed2e57dd40f16f70c63f96a281ec8fd249b85ce1a96a5cab0dd75` (verdict `nonconform`, code 1)
- Blockchain: local Anvil chain id 31337, tx `0x92038e82103638376c9357bea1f36a11039311dfac1a732bb564ab1ccd4b949d`, receipt status 1
- Read-back: MATCH
- Remaining: None
- Next: TASK-003, pending authorization

### TASK-003A — Demo Data Export
- Status: COMPLETE
- Changed: `contracts/smoke_test_real_evidence.py`, `contracts/README.md`, `tests/test_demo_export.py` (new), `data/demo/latest_proof.json` (generated), `audit.md`
- Done: The real-evidence demonstration now publishes an atomic, integrity-checked JSON summary (satellite result, canonical evidence, local-chain record, limitations) after every check passes; a failed run removes any stale document.
- Tests: new focused tests 15 passed; full Python 565 passed, 0 failed; `forge test -vv` 15 passed; real demo exit 0; failure path verified (exit 1, stale document removed).
- Output: `data/demo/latest_proof.json`
- Blockchain: local Anvil chain id 31337, tx `0x78187395d4c1e9bafda1df8d571318109b83e15839a9bee408d75e62ec4d86a7`, receipt status 1
- Integrity: MATCH
- Remaining: None
- Next: TASK-003B — Minimal Read-Only Demo Interface

### TASK-003B — Read-Only Demo Interface
- Status: COMPLETE
- Changed: `demo/index.html`, `demo/styles.css`, `demo/app.js`, `demo/README.md` (new), `scripts/serve_demo.py` (new), `tests/test_demo_server.py` (new), `README.md`, `audit.md`
- Done: A standalone read-only page renders the real `data/demo/latest_proof.json` (no hardcoded values); a stdlib-only localhost server exposes only the page, its assets and `/api/proof`.
- Tests: new focused tests 16 passed; full Python 581 passed, 0 failed (1 skipped when no local Anvil runs); `forge test -vv` 15 passed; headless Chrome render verified real values, error panel hidden.
- Demo URL: http://127.0.0.1:8090/
- Data: data/demo/latest_proof.json
- Limitations: browser checked via headless Chrome DOM dump only; no screenshot/visual regression; the page shows a snapshot, not live chain state.
- Remaining: None
- Next: TASK-003C — Demo Reproducibility and Walkthrough

### Frontend Recovery Assessment

- Status: FOUND
- Location: `origin/main` + `origin/feat/oana-parcel-integration`, path `frontend/` — React 19 + Vite 8 + TS + Tailwind 4, 13 commits
- Build: PASS (isolated checkout: npm ci, tsc, eslint, vite build OK; needs the rolldown native binding, Node 22.11 < Vite 22.12)
- Existing functionality: AppShell, 6-step rail, working ParcelsPage (typed API client); HistoryPage is a placeholder; steps 03-06 absent
- Recommendation: hybrid — keep the proven read-only demo for Oct 25, recover Oana's frontend after
- Next: restore `frontend/` from origin/main (plus its newer `demo.json`), add one step-05 proof page for `data/demo/latest_proof.json`

#### Correction to the previous audit

The earlier emergency audit concluded that **no frontend exists**. That was wrong: it inspected
only the current feature branch. The team's frontend was never lost — it is fully present in
accessible Git history and is functional. Nothing was checked out, merged, reset or cherry-picked
for this assessment; every file was read with `git show` / `git ls-tree` / `git archive` into a
temporary directory outside the repository, and all uncommitted work was preserved.

#### Where it lives

| Ref | Commit | Content |
|---|---|---|
| `origin/main` (= `origin/HEAD`) | `8ad736a` | `frontend/` — 27 files; newest frontend commit `76f5e44 feat(frontend): add field history navigation and plan API client` |
| `origin/feat/oana-parcel-integration` | `65d3ca0` | same application one commit earlier (no `HistoryPage`) |

13 frontend commits, from `935fc74 chore(frontend): initialize React Vite project` to `76f5e44`.
Stack: React 19.3, Vite 8.3, TypeScript 5.9, Tailwind 4.3, react-router-dom 7.18, ethers 6.17,
recharts 3.10, qrcode.react 4.2, lucide-react 1.59. `frontend/src/styles/tokens.css` implements
the `DESIGN_OANA.md` palette exactly (`--navy-950`, `--red-700`, `--paper`, `--font-display` …).

#### Build status: PASS

Run in an isolated copy of `origin/main:frontend/` (never the original):

```text
npm ci                    -> OK, 225 packages
npx tsc -b                -> exit 0
npx eslint .              -> exit 0
npm run build             -> exit 0   (21 modules -> dist/index.html 0.45 kB, CSS 18.96 kB, JS 234.47 kB)
vite preview + headless Chrome -> app boots, renders the shell and its designed error states
```

One environment caveat, not a code defect: this machine runs **Node v22.11.0**, while Vite 8
requires `^20.19.0 || >=22.12.0`. npm therefore skipped the optional native package
`@rolldown/binding-win32-x64-msvc` and `vite build` failed with
`Cannot find module '@rolldown/binding-win32-x64-msvc'`. Installing that single optional package
explicitly (`npm i --no-save --force @rolldown/binding-win32-x64-msvc@1.2.14`) made the build
pass. No newer Node is installed on this machine and there is no nvm.

The built application was rendered with headless Chrome (`vite preview`, port 4173). It shows the
`TERRACYCLE / PROOF` header, the six-step rail (01 Choose a field, 02 Field history,
03 Rotation options, 04 Commitment, 05 Verification, 06 Digital passport), the step-01 page
("A claim is not a proof." / "Field selection") and its honest error state
(`PARCEL DATA UNAVAILABLE` / `API CONFIGURATION ERROR` / "API base URL is not configured"),
because no `VITE_API_BASE_URL` was set for that isolated build.

#### What is real, what is a placeholder, what is missing

| Part | State | Detail |
|---|---|---|
| `components/AppShell.tsx` (29 lines) | working | header, footer, `--paper`/`--navy-950` surfaces |
| `components/StepProgress.tsx` (105 lines) | working | the 6-step rail, `prefers-reduced-motion` aware |
| `pages/ParcelsPage.tsx` (301 lines) | working | real `GET /api/v1/parcels`, typed client, loading/empty/error states, keyboard accessible selection |
| `lib/api.ts` (234 lines) | working | strict runtime validation of parcels and plan responses, `ApiError` with stable codes |
| `pages/HistoryPage.tsx` (48 lines) | **placeholder** | prints only the selected parcel id and "Demo fixture - not satellite-verified." |
| steps 03-06 (`PlanPage`, `CommitmentPage`, `VerificationPage`, `PassportPage`) | **absent** | these files do not exist in any ref |
| `ethers`, `recharts`, `qrcode.react`, `react-router-dom` | **declared, never imported** | no blockchain, chart, QR or routing code exists yet |
| frontend tests | **none** | no test runner, no test files in any ref |

**Consequence:** the frontend is a professional, working shell, but it contains **no verification
and no blockchain page** — precisely the two things a hackathon judge needs. It cannot display the
verified satellite verdict, the canonical evidence hash or the local-chain record today.

#### Two API-contract mismatches (the frontend is written against a newer backend)

1. `lib/types.ts` requires `latitude` and `longitude` on every `Parcel`, but
   `GET /api/v1/parcels` on this branch returns the fixture records unchanged and they have **no
   coordinates** — so `isParcel()` rejects all three parcels and step 01 errors out.
   `origin/main:data/fixtures/demo.json` **does** add them (44.3302/23.7949, 44.5422/26.2697,
   45.6553/25.5879), which is what the frontend expects.
2. `lib/types.ts` requires `climate_source` on `PlanResponse`; this branch's
   `backend/schemas.py::PlanResponse` has only `plan_id`, `parcel_id`, `season_id`, `rotations`.
   `origin/main` adds it via `backend/migrations/versions/a1b2c3d4e5f6_add_climate_source_to_plans.py`
   plus `backend/services/climate_service.py`. (`createPlan()` is not called by any page yet, so
   this one has no runtime impact today.)

#### The larger finding: `origin/main` is ahead of this branch

My branch base `310ce93` **is an ancestor of `origin/main`**, so `origin/main` contains everything
this branch had plus **44 further files**, including a much larger backend:

```text
backend/api/v1/evidence.py          GET /evidence/{evidence_id}/snapshot (canonical bytes)
backend/api/v1/passports.py         GET /passports/{commitment_id} (verdict, hashes, tx hashes)
backend/api/v1/transactions.py      backend/api/v1/climate.py
backend/services/chain_service.py   backend/services/climate_service.py
backend/signer/sign_verdict.mjs     the Node EIP-712 signer
contracts/src/TerraCycleEscrow.sol  contracts/test/TerraCycleEscrow.t.sol
data/climate/parcel_01_season-2024.json
tests/test_evidence_schema.py  tests/test_passports.py  tests/test_plans.py
docs/decisions.md  scripts/demo_tx_mismatch.py
```

`origin/main:backend/api/v1/commitments.py` still contains **both** defects repaired in TASK-001
and TASK-001B (`parcels.setdefault(...)` and `"selected_rotation": rotation` with a float score), so
those fixes are not yet on `main`. `origin/main:/api/v1/config` also advertises `chain_id 11155111`
(Sepolia) with `contract_address: null`, and its `abi_url` (`/api/v1/config/abi`) returns 404.

#### Option A — Oana's frontend vs Option B — our read-only demo

| | A. `frontend/` (origin/main) | B. `demo/index.html` (TASK-003B) |
|---|---|---|
| Design | Full design system, 6-step narrative | Single dashboard, same design tokens |
| Coverage | 1 of 6 steps implemented, 1 placeholder | All six sections on one page |
| **Shows the real satellite + blockchain proof** | **No** — no verification/blockchain page exists | **Yes** — real verdict, canonical hash, local tx, receipt status, event, read-back `MATCH`, integrity flags, limitations |
| Backend coupling | Needs origin/main's backend + fixture | None (static JSON) |
| Build | Needs Node >= 22.12 (or the optional native dep) | None, no framework, no build step |
| Tests | None | 16 focused + 581 Python + headless-Chrome render |

#### Recommendation: hybrid, sequenced

Use **B for the Oct 25 presentation**: it is the only surface that today shows the genuine
satellite verdict (`nonconform`, code 1), the canonical evidence hash
`0x281cf44e592ed2e57dd40f16f70c63f96a281ec8fd249b85ce1a96a5cab0dd75`, the local Anvil
transaction with receipt status 1, the emitted event values and the on-chain read-back match —
all from `data/demo/latest_proof.json`, all verified by 581 Python tests, 15 Solidity tests and a
real browser render. Then recover Oana's work as the frame around it. Do **not** rebuild what
already exists.

#### Smallest integration task (not implemented)

**Restore (no merge, no branch switch):**

```bash
git checkout origin/main -- frontend/
git checkout origin/main -- data/fixtures/demo.json     # brings latitude/longitude
```

**New files (2):**

- `frontend/src/lib/proof.ts` — typed + runtime-validated client for the `demo-proof-v1` schema,
  written in the same style as `lib/api.ts` (`ApiError`, stable error codes, `buildApiUrl`).
  Base URL from `VITE_PROOF_BASE_URL`, or a Vite dev proxy to `scripts/serve_demo.py`.
- `frontend/src/pages/ProofPage.tsx` — step "05 / VERIFICATION": parcel and satellite evidence,
  the verdict with its colour, the canonical evidence block, the local-chain record and the
  limitations, using the existing Tailwind tokens and `AppShell`/`StepProgress`.

**Changed files (4):**

- `frontend/src/lib/types.ts` — add the `demo-proof-v1` types.
- `frontend/src/App.tsx` — route to the proof page (step 5).
- `frontend/src/components/StepProgress.tsx` — step label / index for the proof page.
- `frontend/.env.example` — document `VITE_PROOF_BASE_URL`.

**Dependencies:** none new. No `ethers`, `qrcode.react` or `recharts` is needed for a read-only
proof page.

**Acceptance criteria:**

1. `npm ci && npm run build` passes, `npx tsc -b` and `npx eslint .` clean (Node >= 22.12).
2. The proof page renders the real values from `data/demo/latest_proof.json`: `parcel_01`,
   `nonconform` (code 1), `0x281cf44e…dd75`, receipt status `1`, read-back `MATCH`.
3. The page shows the "Local Anvil — not a public testnet" label and the limitations; it must not
   claim organic certification, public-testnet deployment, EIP-712 settlement or payment.
4. Step 01 still loads the parcels (requires origin/main's `demo.json` coordinates, or relaxing
   `isParcel()`).
5. No evidence value is hardcoded in `frontend/src` (no `0x` + 40/64-hex literal).
6. The page performs no blockchain transaction and contacts only the local API/proof endpoint.

**Tests to add:**

- `tests/test_demo_frontend.py` — asserts `types.ts`/`proof.ts` match the `demo-proof-v1` schema
  (no field drift), that no `0x`-hex evidence literal exists in `frontend/src`, and that the
  frontend's proof URL is served by `scripts/serve_demo.py` (`/api/proof`).
- A headless-Chrome DOM check of the built proof page asserting the rendered evidence hash,
  receipt status and `MATCH` — the same technique used for the read-only demo.
- Regression: the existing 581 Python tests and 15 Solidity tests stay green.

#### Next

Restore `frontend/` from `origin/main` and add the single step-05 proof page, keeping
`demo/index.html` as the proven fallback for the Oct 25 presentation.

### TASK-003D.1 — Frontend Recovery
- Status: COMPLETE
- Source: origin/main:frontend/
- Changed: `frontend/` — 27 files, byte-identical to origin/main
- Done: Restored the React/Vite/TS/Tailwind frontend via `git restore --source=origin/main --worktree -- frontend/`; no merge, no branch switch.
- Build: PASS (npm ci + vite build; needed optional `@rolldown/binding-win32-x64-msvc` — Node 22.11 < Vite 22.12; manifests unchanged)
- TypeScript: PASS
- ESLint: PASS
- Browser: PASS (headless Chrome: shell, six-step rail, parcel page)
- Existing demo: PRESERVED (checksums unchanged; pytest 581 passed)
- Remaining: parcel selection errors (INVALID_RESPONSE) — parcel payload lacks `latitude`/`longitude`
- Next: TASK-003D.2 — React Proof Page
