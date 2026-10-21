# TerraCycle Evidence Registry (TASK-002A)

Minimal, append-only Solidity registry that records the **canonical evidence hash** and the
**verifier verdict** of a TerraCycle commitment.

- **Contract**: `contracts/src/TerraCycleEvidenceRegistry.sol`
- **Tests**: `contracts/test/TerraCycleEvidenceRegistry.t.sol` (15 tests)
- **ABI**: `contracts/abi/TerraCycleEvidenceRegistry.json`
- **Toolchain**: Foundry (`forge`), Solidity `0.8.24`, `forge-std` `v1.17.0` (git submodule)

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

It is **not** a drop-in replacement for the planned `TerraCycleEscrow` contract (see
`TerraCycleEscrow.sol` on `origin/main`, which keeps escrow, EIP-712 and settlement).

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

Dependencies are vendored as git submodules, matching the convention already used on the
`origin/feat/shit` branch:

```bash
git submodule update --init --recursive
```
