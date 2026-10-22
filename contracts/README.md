# TerraCycle Solidity contracts

This project holds **two separate, independently identifiable contracts**:

| Contract | Source | Purpose |
|---|---|---|
| `TerraCycleEvidenceRegistry` | TASK-002A | Minimal, append-only Solidity registry that records the **canonical evidence hash** and the **verifier verdict** of a TerraCycle commitment. Holds no ETH. |
| `TerraCycleEscrow` | TASK-004A | Commitment lifecycle with ETH escrow: register, fund, EIP-712-authorised settlement, refund. |

## TerraCycle Evidence Registry (TASK-002A)

- **Contract**: `contracts/src/TerraCycleEvidenceRegistry.sol`
- **Tests**: `contracts/test/TerraCycleEvidenceRegistry.t.sol` (15 tests)
- **ABI**: `contracts/abi/TerraCycleEvidenceRegistry.json`
- **Toolchain**: Foundry (`forge`), Solidity `0.8.24`, `forge-std` `v1.17.0` and OpenZeppelin Contracts `v5.7.0` (git submodules)

## Constructor

```solidity
constructor(address verifier_)
```

`verifier_` is the **only** address allowed to record evidence. It cannot be the zero address
(`ZeroVerifierAddress`). It is stored as an `immutable`: there is no rotation function, so changing
the verifier requires a new deployment.

## Public functions

| Function | Mutability | Description |
|---|---|---|
| `recordEvidence(bytes32 commitmentId, bytes32 evidenceHash, uint8 verdict)` | nonpayable | Records one evidence record. Verifier only. |
| `getEvidence(bytes32 commitmentId)` | view | Returns the stored `Evidence` struct (zeroed if unknown). |
| `hasEvidence(bytes32 commitmentId)` | view | `true` once a commitment id carries evidence. |
| `verifier()` | view | The authorized verifier address. |
| `VERDICT_CONFORM()` / `VERDICT_NONCONFORM()` / `VERDICT_INCONCLUSIVE()` | view | The TerraCycle verdict codes. |

`recordEvidence` reverts with a custom error when:

| Error | Condition |
|---|---|
| `NotVerifier()` | `msg.sender != verifier` |
| `ZeroCommitmentId()` | `commitmentId == bytes32(0)` |
| `ZeroEvidenceHash()` | `evidenceHash == bytes32(0)` |
| `InvalidVerdict()` | `verdict > 2` |
| `EvidenceAlreadyRecorded()` | the commitment id already carries evidence |

## Event

```solidity
event EvidenceRecorded(
    bytes32 indexed commitmentId,
    bytes32 indexed evidenceHash,
    uint8  indexed verdict,
    address recorder,
    uint256 recordedAt
);
```

`recorder` and `recordedAt` are in the event data (not indexed), so a consumer can read the whole
record from the log.

## Access control

A single immutable address set at construction. There is no owner, no role system and no
admin function — the authorized verifier is the only writer, and the contract has no other
privileged path. Records are **immutable**: a commitment id can be recorded exactly once.

## Verdict representation

The TerraCycle mapping from `Agent.md`:

| JSON | uint8 | Meaning |
|---|---:|---|
| `conform` | `0` | Observations meet the frozen policy |
| `nonconform` | `1` | Enough observations, condition not met |
| `inconclusive` | `2` | Insufficient data — no failure is claimed |

Any other value is rejected.

## What this contract does NOT do

- It does **not** transfer, hold or escrow ETH (there is no payable function).
- It does **not** implement EIP-712, does not verify signatures and does not sign attestations.
- It does **not** register farming plans and does **not** settle or refund anything.
- It does **not** verify satellite data and does **not** claim that NDVI establishes organic
  certification.
- It does **not** recompute or validate the evidence hash: the hash is computed off-chain by the
  backend over the canonical evidence document bytes. This contract only records what an
  authorized party submits.

It is **not** a drop-in replacement for the `TerraCycleEscrow` contract, which now lives in
this same project at `contracts/src/TerraCycleEscrow.sol` (see below). The two contracts are
deliberately separate and separately identifiable:

| Contract | Holds ETH | Purpose |
|---|---|---|
| `TerraCycleEvidenceRegistry` | no | Append-only record of an evidence hash + verdict |
| `TerraCycleEscrow` | yes | Commitment lifecycle: register, fund, settle, refund |

## The escrow contract (TASK-004A)

Recovered from `origin/main` (`cab1993…` era) and validated locally. It is **not** wired to
the backend yet — that is TASK-004B.

- **Contract**: `contracts/src/TerraCycleEscrow.sol`
- **Tests**: `contracts/test/TerraCycleEscrow.t.sol` (16), `contracts/test/TerraCycleEscrowSecurity.t.sol` (34),
  `contracts/test/TerraCycleEscrowZeroBeneficiary.t.sol` (11),
  `contracts/test/TerraCycleEscrowRegistrationAuth.t.sol` (16),
  `contracts/test/TerraCycleEscrowInvariant.t.sol` (6 invariants)
- **ABI**: `contracts/abi/TerraCycleEscrow.json`
- **Dependencies**: OpenZeppelin Contracts **v5.7.0** (git submodule, pinned in `foundry.lock`)

### The trust model

The contract has **four distinct roles**. Two of them are on-chain authorities,
set once at deployment and stored as `immutable`; the other two are per-commitment.

| Role | On chain? | Who it is | What it may do |
|---|---|---|---|
| **registrar** | yes, `immutable` | the authority that allocates commitment ids | call `registerCommitment` — **and nothing else** |
| **verifier** | yes, `immutable` | the authority that signs verdicts | sign an EIP-712 attestation that `settle` accepts — **and nothing else** |
| **beneficiary** | per commitment | the farmer who is paid | receive the reward; **cannot** register or settle |
| **funder** | per commitment | the buyer who pays | fund the commitment and reclaim it via `refund`; **cannot** register or settle |

```solidity
constructor(address verifier_, address registrar_, string memory name, string memory version)
```

The **registrar and the verifier are deliberately separate addresses**. A compromised
verifier cannot create commitments, and a compromised registrar cannot forge verdicts.
Neither role can be rotated: both are `immutable`, so changing either requires a new
deployment. The contract deliberately has **no owner, no admin and no upgrade path**.

#### Why a registrar role is necessary

The commitment id is `keccak256(abi.encode(parcelId, seasonId))` — it does **not**
depend on the beneficiary. `registeredId` is never cleared. So *any* account could
reserve a `(parcel, season)` id permanently and lock the legitimate farmer out of that
parcel for that season, simply by calling `registerCommitment` first. A rule of the
form `msg.sender == beneficiary` would **not** prevent this, because an attacker can
register with themselves as the beneficiary. Only a trusted allocator of ids closes
the hole.

#### The trust assumption (explicit)

The project's architecture names the actor of a registration as the **farmer**
(`TerraCycle_Ghid_Integrare.md` §"MetaMask: registerCommitment(...)", and
`docs/api-contract.md` → `"tx_type": "register_commitment", "actor": "farmer"`), and
specifies that `/commitments/{id}/transactions` must verify "actors". The transition
table, however, gives `refund` an explicit `msg.sender == funder` rule and gives
`registerCommitment` **none** — that missing rule is the gap this task closes.

**The MVP assumption is a single trusted registrar.** For the local MVP that is one
Anvil development account (`0x90F79bf6…`, account #3) standing in for the farmer
registry. **The role IS centralized**: whoever holds that address can register any
commitment for any beneficiary, and can therefore squat ids. A production design
would replace it with a farmer registry (a contract that verifies a farmer's identity
and forwards the registration), which would keep the same contract interface. That
is **not** implemented here, and the escrow is **not production-secure**.

#### What an unauthorized account cannot do

- it cannot register a commitment, so it cannot reserve a commitment id;
- it cannot squat a `(parcel, season)` pair;
- it cannot emit a `CommitmentRegistered` event;
- it cannot change any existing commitment: there is no setter for the beneficiary,
  the plan hash, the reward or the deadline.

#### How the backend will eventually submit registrations

The backend already prepares the commitment off-chain (`POST /commitments/prepare`
creates the snapshot and the `plan_hash`) and then **records** a mined registration
transaction (`POST /commitments/{id}/transactions`, `tx_type: "register_commitment"`,
`actor: "farmer"`). It does not send it: the farmer's wallet does, through MetaMask.
The backend's checker (`backend/services/chain_service.py::_check_register`, currently
only on `origin/main`) validates `parcelId`, `seasonId` and `planHash` — it does **not**
yet check `tx["from"]` against the registrar. That backend check is a separate task
(TASK-004B.2); the contract already enforces it.

### State machine

```text
None ──registerCommitment──> Registered ──fundCommitment──> Funded
                                                              │
                          settle(conform = 0) ────────────────┼──> Paid       (beneficiary paid)
                          settle(nonconform/inconclusive) ─────┴──> Negative  (funder may refund)

Negative   ──refund──> Refunded
Funded     ──refund (only after settleDeadline)──> Refunded
```

`settle` requires an EIP-712 signature from the immutable `verifier`. The digest binds
`commitmentId`, `planHash`, `evidenceHash`, `verdict` and `validUntil`, so a signed
attestation is bound to exactly one commitment and can be consumed exactly once.

### Fixed vulnerability: unauthorized commitment registration (TASK-004B.2B)

**The bug.** `registerCommitment` had **no `msg.sender` condition**, so any account
could create a commitment for any `(parcel, season)` pair and permanently reserve that
commitment id, locking the legitimate farmer out.

**The fix.** A new `NotRegistrar()` error and a check at the top of
`registerCommitment`:

```solidity
if (msg.sender != registrar) {
    revert NotRegistrar();
}
```

The check runs **before** the duplicate, plan-hash and beneficiary checks, so an
unauthorized caller learns nothing about whether a commitment id exists. The
authorization decision is made by the contract, not by the backend.

Coverage: `contracts/test/TerraCycleEscrowRegistrationAuth.t.sol` (16 tests, including
a fuzz test over the caller address, the parcel, the season and the plan hash) plus two
new invariants in `contracts/test/TerraCycleEscrowInvariant.t.sol` — an unauthorized
registration must never succeed, and it must always fail with `NotRegistrar()`.

### Fixed vulnerability: zero-address payout (TASK-004B.2A)

**The bug.** `registerCommitment` accepted `address(0)` as the payout beneficiary.
A transfer to the zero address **succeeds** in the EVM — `payable(address(0)).call{
value: amount}("")` returns `ok == true` — so during settlement the escrowed reward
left the contract, the commitment was marked `Paid` and the funds became
**irrecoverable**: nobody controls `address(0)`. Reproduced in the local test EVM
before the fix:

```text
VULNERABLE: escrow balance before settle: 1000000000000000000
VULNERABLE: escrow balance after  settle: 0
VULNERABLE: address(0) balance before: 0
VULNERABLE: address(0) balance after : 1000000000000000000
VULNERABLE: commitment reward recorded : 0
VULNERABLE: commitment state (2=Funded,3=Paid): 3
```

The escrow's own accounting still balanced (`balance == sum(rewards)`), which is why
the invariant suite did not catch it: the money was not lost *by the contract*, it was
lost *to the zero address*.

**The fix.** Two guards, both raising the new `ZeroBeneficiary()` error:

1. `registerCommitment` rejects a zero beneficiary. The beneficiary is supplied
   **only** here and there is no setter, so this is the earliest and only boundary
   at which the value can be refused. The check sits **after** the existing
   `CommitmentAlreadyRegistered` and `InvalidPlanHash` checks, so the error
   precedence of every pre-existing input is unchanged.
2. `_payBeneficiary` re-checks the beneficiary before moving any ETH. This is
   unreachable today (guard 1 makes it so), but the payout boundary itself must
   never be able to burn escrowed funds, even if a later change introduces another
   path that sets a beneficiary.

No economic rule changed: payouts, percentages, rewards, deadlines, verdict handling
and the refund path are untouched.

Coverage: `contracts/test/TerraCycleEscrowZeroBeneficiary.t.sol` (11 tests, including
a fuzz test over the beneficiary address) plus two new invariants in
`contracts/test/TerraCycleEscrowInvariant.t.sol` — no commitment may ever carry a zero
beneficiary, and a zero-beneficiary registration must never succeed.

### Known gaps (reported, not silently changed)

**These three remain OPEN. The escrow is NOT production-secure or production-ready.**

| Gap | Impact | Status |
|---|---|---|
| The agreed reward amount is not bound on-chain | a funder can fund with 1 wei; the amount is only checked off-chain by `chain_service` | **open** — needs an ABI/business-rule change |
| `settle` ignores `settleDeadline` | a verifier can settle after the deadline, when the funder already had the right to refund | **open** — needs a business decision |
| `CommitmentSettled` does not emit `evidenceHash` | the on-chain settlement cannot be linked to the SHA-256 evidence hash from the log alone | **open** — ABI change, needed for TASK-004B |

Also still open, and not addressed by TASK-004B.2A or TASK-004B.2B:

| Gap | Impact | Status |
|---|---|---|
| The registrar role is a single trusted address | whoever holds it can register any commitment and squat ids | **open** — the MVP assumption; a farmer-registry contract is the production answer |
| `settleDeadline` is not validated at registration | a commitment can be registered with an already-expired deadline, so a funder can fund and immediately refund | **open** |
| `settle` does not reject a zero `evidenceHash` | the evidence registry rejects it, the escrow does not | **open** |
| No rescue path | ETH forced in via `selfdestruct` is stuck forever | **open** — low severity, no reachable path today |

The corresponding behaviour is pinned by executable characterisation tests named
`test_FINDING_*` in `contracts/test/TerraCycleEscrowSecurity.t.sol`, so no gap can be
closed by accident.

### EIP-712 interoperability (TASK-004B.1)

The Node signer (`backend/signer/sign_verdict.mjs`) now produces a real EIP-712
signature that the deployed escrow **accepts** on a local Anvil chain, over
genuine Sentinel-2 evidence (`nonconform`, code 1). The check is a simulation
(`eth_call`): nothing is settled, no refund is sent, no beneficiary is paid.

```powershell
cd contracts
.\.foundry\forge.exe build
.\.foundry\anvil.exe --host 127.0.0.1 --port 8547 --chain-id 31337   # terminal 1

# terminal 2
$env:ANVIL_RPC_URL = "http://127.0.0.1:8547"
$env:ANVIL_PRIVATE_KEY = "<anvil development key>"
$env:VERIFIER_PRIVATE_KEY = $env:ANVIL_PRIVATE_KEY
..\.venv\Scripts\python.exe verify_eip712_signature.py
```

The full workflow, the EIP-712 domain, the SHA-256 vs Keccak-256 distinction and
the negative-test matrix are documented in
[`../docs/eip712-signing.md`](../docs/eip712-signing.md).

## Backend integration (TASK-002B)

The values are the same ones the backend already produces, so no new hashing rules are needed:

| Contract parameter | Backend value | Source |
|---|---|---|
| `commitmentId` | `0x` + 64 hex | `compute_commitment_id(parcel_id_bytes32, season_id_bytes32)` — `backend/hashing.py` |
| `evidenceHash` | `0x` + 64 hex | SHA-256 over the canonical evidence document bytes — `backend/services/evidence_builder.py` |
| `verdict` | `uint8` 0/1/2 | `verdict_code` from the verifier — `backend/ml/rules.py` |

Minimal work required later:

1. Deploy the registry with the address of the authorized verifier (the account that holds
   `VERIFIER_PRIVATE_KEY` for `backend/signer/sign_verdict.mjs`).
2. Publish the ABI. The backend already advertises `"abi_url": "/api/v1/config/abi"` in
   `backend/api/v1/config.py`, but no such route exists yet; the ABI is at
   `contracts/abi/TerraCycleEvidenceRegistry.json`.
3. Set `contract_address` and `verifier_address` in `backend/api/v1/config.py` (currently `None`).
4. Have the backend submit `recordEvidence(commitment_id, evidence_hash, verdict_code)` from the
   authorized verifier account, and read it back with `getEvidence` / the `EvidenceRecorded` log.

## Build and test

```bash
cd contracts
forge build
forge test -vv
```

The tests run entirely on the local EVM: no RPC endpoint, no fork, no network access and no ETH
is moved.

## Local blockchain demo (Anvil)

The registry can be deployed to a **local** Anvil chain and exercised with one real transaction.

> For the complete, tested Windows startup of the whole demo — Anvil, the real satellite
> evidence run, FastAPI, the proof server, React and both surfaces — see
> [`../demo/README.md`](../demo/README.md).

Two scripts are available:

| Script | Evidence |
|---|---|
| `smoke_test.py` | synthetic **TEST** values (see below) |
| `smoke_test_real_evidence.py` | **genuine** satellite-derived evidence (see the next section) |

> This runs **only on a local blockchain**. No real ETH is used, no public network is contacted
> and no real wallet credentials are involved. The commitment id and evidence hash recorded by
> the `smoke_test.py` demo are **TEST values** for this task — they are not satellite-derived
> evidence and they do not describe any agricultural parcel. This registry is **not** the full
> escrow contract: there is no funding, no settlement, no refund and no EIP-712 signing.

### 1. Start a local chain

The project documents `CHAIN_RPC_URL=http://127.0.0.1:8545` and `CHAIN_ID=31337`
(`Role_Corina.md`). Anvil prints its development accounts and keys on startup — copy one of them
into the `ANVIL_PRIVATE_KEY` environment variable. **Never commit a key or a `.env` file.**

```bash
cd contracts
anvil --host 127.0.0.1 --port 8545 --chain-id 31337
```

### 2. Run the smoke test

In a second terminal:

```bash
cd contracts
forge build                       # the deployment bytecode comes from the Foundry artifact
export ANVIL_RPC_URL=http://127.0.0.1:8545
export ANVIL_PRIVATE_KEY=<one of the development keys Anvil printed>
python smoke_test.py
```

`smoke_test.py` (Web3, already a backend dependency) deploys the registry, records one evidence
entry with deterministic TEST values, then verifies:

- the chain is reachable and runs on the documented local chain id `31337`;
- the deployment transaction succeeded;
- the authorized verifier on chain is the one given to the constructor;
- the evidence transaction receipt has status `1` and targets the registry;
- exactly one `EvidenceRecorded` event was emitted, with the expected commitment id, evidence
  hash, verdict, recorder and timestamp;
- `getEvidence()` returns exactly the submitted values, and `hasEvidence()` is `true`.

It prints the registry address and the transaction hash, and **exits non-zero** if any check
fails. Set `REGISTRY_ADDRESS` to reuse an already deployed registry instead of deploying a new
one; set `REGISTRY_VERIFIER` to use a verifier address other than the deployer.

### 3. Manual equivalent with Foundry tools

```bash
# Deploy (note: --constructor-args is variadic, so it must come last)
forge create src/TerraCycleEvidenceRegistry.sol:TerraCycleEvidenceRegistry \
  --rpc-url http://127.0.0.1:8545 --private-key $ANVIL_PRIVATE_KEY --broadcast \
  --constructor-args 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266

# Record one evidence entry (TEST values, verdict 0 = conform)
cast send <REGISTRY> "recordEvidence(bytes32,bytes32,uint8)" \
  0x7465737400000000000000000000000000000000000000000000000000000001 \
  0x7465737400000000000000000000000000000000000000000000000000000002 0 \
  --rpc-url http://127.0.0.1:8545 --private-key $ANVIL_PRIVATE_KEY

# Read it back
cast call <REGISTRY> "getEvidence(bytes32)((bytes32,bytes32,uint8,uint256,address))" \
  0x7465737400000000000000000000000000000000000000000000000000000001 \
  --rpc-url http://127.0.0.1:8545
```

Recording the same commitment id twice reverts with `EvidenceAlreadyRecorded`.

## Real satellite evidence on a local chain

`smoke_test_real_evidence.py` replaces the synthetic values above with **genuine evidence**
generated by the existing pipeline:

```
backend/api/v1/plans.py        ->  a real plan
backend/api/v1/commitments.py  ->  a real commitment (real commitment_id, real plan_hash)
backend/ml/rules.py            ->  the scientific verifier on the real Sentinel-2 CSV of parcel_01
backend/services/evidence_builder.py  ->  the canonical evidence document
backend/hashing.py             ->  canonical bytes + SHA-256 evidence hash
```

Nothing is re-implemented and nothing is invented: the commitment comes from the authoritative
preparation flow, the observations come from the real `data/ndvi/parcel_01_2024_quality.csv`
export (Copernicus Data Space / Sentinel-2 L2A), the verdict is whatever the verifier returns,
and the hash is recomputed from the canonical bytes.

The signed verification endpoint is **not** called: it would require the Node signer, which is
out of scope. Everything up to and including the canonical evidence hash is the existing
implementation.

### Reproduce

```bash
cd contracts
forge build                                   # creation bytecode for the deployment
anvil --host 127.0.0.1 --port 8545 --chain-id 31337      # terminal 1
```

```bash
cd contracts
export ANVIL_RPC_URL=http://127.0.0.1:8545
export ANVIL_PRIVATE_KEY=<a development key Anvil printed>
python smoke_test_real_evidence.py            # terminal 2
```

Local configuration: `ANVIL_RPC_URL` (default `http://127.0.0.1:8545`), `ANVIL_PRIVATE_KEY`
(required, from the Anvil startup banner — never commit it), and optionally `REGISTRY_ADDRESS`
(reuse a deployment) or `REGISTRY_VERIFIER` (record as a different authorized address).

### Output fields

| Field | Meaning |
|---|---|
| `Parcel`, `Season`, `Policy` | the verified parcel, season and frozen policy |
| `Source CSV`, `Provider` | the real Sentinel-2 export used |
| `Verdict`, `Reason`, `Reason code` | the scientific verifier result, verbatim |
| `Observations`, `Evidence quality` | observation counts, quality and temporal coverage |
| `Plan id`, `Commitment id`, `Plan hash` | from the authoritative preparation flow |
| `Evidence bytes`, `Evidence hash` | canonical evidence document size and its SHA-256 |
| `Registry`, `Deploy tx` | local deployment address and transaction |
| `Evidence tx` | the mined transaction hash and its receipt status |

### Presentation summary (`data/demo/latest_proof.json`)

A successful run can publish a machine-readable summary for a future read-only interface:

```bash
cd contracts
python smoke_test_real_evidence.py --output ../data/demo/latest_proof.json
```

The document is written **only after every integrity check passed**, and it is written
**atomically** (a partial file is never left behind). The checks are:

1. the SHA-256 is recomputed from the canonical evidence bytes and compared with the hash used
   in the transaction;
2. the transaction receipt is successful;
3. the emitted `EvidenceRecorded` event carries the expected commitment id, evidence hash and
   verdict;
4. the values stored on chain equal the generated evidence;
5. the scientific verdict was not modified.

If any check fails the run exits non-zero and **the previous document is removed**, so a failed
run can never leave a success document that a reader could mistake for a current result.

The summary is a **presentation summary only**: the canonical evidence bytes and their SHA-256
hash remain the authoritative artefacts. It is deliberately flat and small:

| Section | Content |
|---|---|
| `run` | status, local-chain identification, chain id, RPC endpoint |
| `parcel` | parcel/season, satellite source, observation counts |
| `verification` | the scientific verdict, policy, window, quality warnings |
| `evidence` | commitment id, evidence id, evidence hash, canonical size |
| `blockchain` | registry address, transaction hashes, receipt status, event, on-chain values |
| `integrity` | the five verification flags above |
| `limitations` | what the result does **not** claim |

No private key, token or credential is ever written: the RPC endpoint is reduced to a
credential-free local URL and any non-local host is redacted.

### What the blockchain actually proves

The registry proves **who** recorded a given evidence hash for a given commitment, **when**, and
that the record has not been altered since. The commitment id and the evidence hash are the
same bytes the backend computed and signed off-chain.

It does **not** prove that the satellite observations are correct, that the practice is
environmentally compliant, that the farmer is organic-certified, or that anyone is entitled to a
payment. Those remain offline, scientific and policy questions.

The three layers stay explicitly separate, in the summary and in this pipeline:

| Layer | What it establishes |
|---|---|
| `verification` | **scientific** — vegetation conditions from Sentinel-2 NDVI over the frozen policy window |
| `evidence` | **cryptographic** — SHA-256 over the canonical evidence bytes; the record is unaltered |
| `blockchain` | **recording** — who stored that hash, on a LOCAL chain, and when |

> **Local Anvil transactions are not public testnet transactions.** They exist only in the
> throwaway local chain and disappear with it. No real ETH is used and no public network is
> contacted.
>
> The registry stores evidence **metadata** only. It does not independently verify satellite
> observations, organic compliance or payment eligibility, and it is not the escrow contract:
> there is no funding, no settlement, no refund and no EIP-712 signing.

### Foundry on Windows

Foundry was not installed on this machine, so it was installed **locally** (no global toolchain
change, no installer script):

```powershell
# 1. Download the official prebuilt binaries and verify the published checksum
$url = "https://github.com/foundry-rs/foundry/releases/download/v1.8.5/foundry_v1.8.5_win32_amd64.zip"
Invoke-WebRequest -Uri $url -OutFile foundry.zip
(Get-FileHash foundry.zip -Algorithm SHA256).Hash.ToLower()   # compare with the published .sha256

# 2. Extract and use
Expand-Archive foundry.zip -DestinationPath .foundry
.\.foundry\forge.exe build
.\.foundry\forge.exe test -vv
```

`forge` also downloads `solc 0.8.24` once into its local cache. `Role_Dorian.md` documents WSL2 as
the team's Windows approach; a WSL2 distribution was not installed on this machine.

Dependencies are vendored as git submodules. Both must be initialised or the build fails:

```bash
git submodule update --init --recursive
```

| Submodule | Version | Pinned in | Required by |
|---|---|---|---|
| `contracts/lib/forge-std` | `v1.17.0` (`f3dae6e`) | `contracts/foundry.lock` | both contracts and all tests |
| `contracts/lib/openzeppelin-contracts` | `v5.7.0` (`cab1993`) | `contracts/foundry.lock` | `TerraCycleEscrow` only (`EIP712`, `ECDSA`, `ReentrancyGuard`) |

> **Note (TASK-004A).** On `origin/main` the `openzeppelin-contracts` gitlink exists in the
> tree but `.gitmodules` does **not** declare it, so `git submodule update --init --recursive`
> never initialises it and `forge build` cannot resolve
> `@openzeppelin/contracts/utils/cryptography/EIP712.sol`. The `.gitmodules` entry is fixed on
> this branch. If a clone fails with an unresolved import, check
> `git submodule status` lists both entries.

The OpenZeppelin version is not arbitrary: the escrow contract uses the **v5** API
(`_hashTypedDataV4`, `ECDSA.recover` reverting on a malformed signature). The v4 API used by
the original test file (`domainSeparatorV4()` as a public function) was removed in v5.
