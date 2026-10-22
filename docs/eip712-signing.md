# EIP-712 signing and cross-language verification (TASK-004B.1)

This document describes the **tested** signing workflow between the Node.js
signer and the Solidity escrow contract, and how to reproduce the local
verification.

> **Nothing here settles money.** The interoperability check is a simulation
> (`eth_call`). No settlement transaction, no refund transaction and no
> beneficiary payment is ever executed. See
> [Why no settlement occurred](#why-no-settlement-occurred).

---

## 1. The two hashes — never confuse them

TerraCycle uses **two different hash algorithms** for two different purposes.
They are never substituted for one another.

| | Evidence hash | EIP-712 digest |
|---|---|---|
| Algorithm | **SHA-256** | **Keccak-256** |
| Input | the canonical evidence document bytes | the domain separator + the struct hash |
| Produced by | `backend/hashing.py::hash_snapshot` (Python) | `ethers` `signTypedData` (Node) |
| Used for | the `evidenceHash` field of the attestation — what the attestation **commits to** | the value that is actually **signed** |
| Length | 32 bytes | 32 bytes |

The canonical evidence document is built by `backend/services/evidence_builder.py`
and serialized by `backend/hashing.py::canonical_bytes` (sorted keys, compact
separators, UTF-8, **floats forbidden**). The evidence hash is
`SHA-256(canonical_bytes)`.

The EIP-712 digest is `keccak256(0x19 0x01 ‖ domainSeparator ‖ structHash)`.

They are different values over different inputs. A regression test
(`tests/test_signer_eip712.py::test_the_sha256_evidence_hash_and_the_keccak256_digest_are_different_values`)
asserts this explicitly.

> The contract stores `evidenceHash` as an opaque 32-byte value. It never
> recomputes it and never validates it: the chain proves that *someone*
> attested to a hash, not that the hash is correct. The hash's correctness is
> established offline, by the pipeline that produced it.

## 2. The EIP-712 struct and the domain

### Struct

The contract declares:

```solidity
struct VerificationResult {
    bytes32 commitmentId;
    bytes32 planHash;
    bytes32 evidenceHash;
    uint8   verdict;
    uint64  validUntil;
}
```

with

```solidity
VERIFIER_TYPEHASH = keccak256(
    "VerificationResult(bytes32 commitmentId,bytes32 planHash,bytes32 evidenceHash,uint8 verdict,uint64 validUntil)"
);
```

The Node signer declares the **same** type, in the **same order**, with the
**same primitive types**:

```javascript
VerificationResult: [
  { name: "commitmentId", type: "bytes32" },
  { name: "planHash",     type: "bytes32" },
  { name: "evidenceHash", type: "bytes32" },
  { name: "verdict",      type: "uint8"   },
  { name: "validUntil",   type: "uint64"  },
]
```

`backend/signer/recover_signer.mjs` deliberately declares **its own copy** of
this type instead of importing it, so that any drift between the signer and the
verifier is *detected* rather than hidden.

### Domain — and how it is obtained

The domain is **read back from the deployed contract** with `eip712Domain()`
(the ERC-5267 interface that OpenZeppelin v5 exposes publicly). The contract
is the authority for its own domain:

```text
name              = "TerraCycleEscrow"     (constructor argument)
version           = "1"                    (constructor argument)
chainId           = 31337                 (the local Anvil chain)
verifyingContract = <address of the deployed escrow>
```

The verification script asserts the fields bitmap is `0x0f` (name, version,
chainId, verifyingContract — no salt, no extensions) and that the name and
version are exactly `TerraCycleEscrow` / `1`.

The domain separator is then
`keccak256(abi.encode(TYPE_HASH, keccak256(name), keccak256(version), chainId, verifyingContract))`,
which is what OpenZeppelin v5 computes in `EIP712._buildDomainSeparator()`.

**The domain must be built from the freshly deployed contract address.** A
signature produced for one deployment is not valid for another: the
interoperability script deploys a second escrow and confirms the first
signature is rejected there.

## 3. Which account acts as the verifier

On the local Anvil chain the **verifier is Anvil development account #0**:

```text
address = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
```

Its private key is Anvil's well-known **development** key. It is printed by
Anvil on startup and is **never committed, never logged and never printed by
the signer**. The contract stores it as an `immutable`, so the verifier cannot
be rotated without a new deployment.

The signer reads it from the `VERIFIER_PRIVATE_KEY` environment variable and
never echoes it.

## 4. The exact tested workflow

```text
 1. backend/api/v1/plans.py          -> a real plan for parcel_01 / season-2024
 2. backend/api/v1/commitments.py    -> a real commitment (commitment_id, plan_hash)
 3. backend/ml/rules.py              -> the real scientific verdict on the real
                                        Sentinel-2 CSV   ("nonconform", code 1)
 4. backend/services/evidence_builder.py
                                     -> the canonical evidence document
 5. backend/hashing.py               -> canonical bytes + SHA-256 evidence hash
 6. build_attestation()              -> {commitmentId, planHash, evidenceHash,
                                         verdict, validUntil}
 7. domain = eip712Domain()          -> read back from the DEPLOYED contract
 8. node backend/signer/sign_verdict.mjs
                                     -> {"signature": "0x…"}  (65 bytes)
 9. ethers (recover_signer.mjs)      -> the recovered signer address
10. eth_call escrow.settle(attestation, signature)
                                     -> the contract ACCEPTS it (simulation)
```

Steps 1–5 are the **existing** pipeline; nothing is re-implemented and no
value is hardcoded. The verification script calls
`contracts/smoke_test_real_evidence.py::generate_real_evidence()`, which runs
the real verifier on `data/ndvi/parcel_01_2024_quality.csv` and returns the
genuine commitment, verdict and evidence hash.

### The real values used in the test

| Field | Value |
|---|---|
| `commitmentId` | `0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871` |
| `planHash` | `0x161e3ed13e04d4916811a5842feb5a01e25ae4ee17439c3bc6b740f7064e5194` |
| `evidenceHash` | `0x281cf44e592ed2e57dd40f16f70c63f96a281ec8fd249b85ce1a96a5cab0dd75` |
| `verdict` | `1` (`nonconform`) |
| `validUntil` | the commitment's `settle_deadline` (now + 30 days) |

The commitment id and the evidence hash are the same values recorded in
`data/demo/latest_proof.json` — they are reproducible because the pipeline is
deterministic.

## 5. How to reproduce the verification

### Prerequisites

```powershell
cd contracts
.\.foundry\forge.exe build          # portable Foundry, see contracts/README.md
```

### Terminal 1 — the local chain

```powershell
cd contracts
.\.foundry\anvil.exe --host 127.0.0.1 --port 8547 --chain-id 31337
```

### Terminal 2 — the interoperability check

```powershell
cd contracts
$env:ANVIL_RPC_URL       = "http://127.0.0.1:8547"
$env:ANVIL_PRIVATE_KEY   = "<anvil development key #0>"
$env:VERIFIER_PRIVATE_KEY = $env:ANVIL_PRIVATE_KEY
..\.venv\Scripts\python.exe verify_eip712_signature.py
```

The script prints a per-check `PASS`/`FAIL` report and exits non-zero if any
check fails.

### The focused test suites

```powershell
# Node: the signer CLI (21 tests)
cd backend\signer
npm install
node --test

# Python: cross-language + the deployed contract (25 tests)
cd <repo root>
.\.venv\Scripts\python.exe -m pytest tests\test_signer_eip712.py -q
```

The Python chain tests are **skipped automatically** when no local Anvil is
reachable, so the suite stays green on a machine without Foundry.

## 6. Why no settlement occurred

`settle()` is invoked with **`eth_call`**, which executes the contract's code
against the current chain state and **discards the result**. No transaction is
broadcast, no block is mined, no state is written.

The script proves this rather than asserting it:

- the commitment state is byte-identical before and after the simulation;
- the commitment is still in state `2` (`Funded`);
- the escrow balance is unchanged;
- the beneficiary balance is unchanged (nothing was paid);
- the latest block number is unchanged (no block was mined).

The **only** transactions sent by the script are `registerCommitment`,
`fundCommitment` (twice, for two commitments) and the escrow **deployments** —
all of them local development ETH on a throwaway chain.

`refund()` is never called.

## 7. Negative tests

Every tampered attestation is submitted to the **deployed contract** and must
be rejected for the intended reason:

| Case | Rejected with |
|---|---|
| signed by the wrong key | `InvalidSignature` |
| signed for the wrong chain id | `InvalidSignature` |
| signed for the wrong contract address | `InvalidSignature` |
| replayed against a different commitment | `InvalidSignature` |
| a different plan hash | `PlanHashMismatch` |
| a modified evidence hash | `InvalidSignature` |
| a modified verdict | `InvalidSignature` |
| an expired `validUntil` | `AttestationExpired` |
| a truncated signature | `ECDSAInvalidSignatureLength` (OpenZeppelin v5) |

Note on the last one: OpenZeppelin v5's `ECDSA.recover` **reverts** on a
malformed signature with its own error instead of returning `address(0)`, so
the error taxonomy differs from the wrong-signer case. The call is still
rejected, which is what matters.

### On replay protection — what is and is not tested

- **Tested:** a signature is bound to exactly one commitment. Replaying it
  against a *different* commitment fails with `InvalidSignature`, because the
  digest includes `commitmentId`.
- **Tested:** a signature is bound to one contract. It does not verify against
  a second deployment at a different address.
- **Tested:** a signed attestation is consumed at most once — the contract's
  state machine leaves the commitment in `Paid`/`Negative`, so a second
  `settle()` reverts with `InvalidState`.
- **NOT claimed:** deadline-based replay protection. `validUntil` is checked
  at settlement time and an expired attestation is rejected with
  `AttestationExpired` (tested), but there is **no nonce** in the struct, so
  the deadline is the only time bound on an attestation.

## 8. The outstanding escrow security findings

These are **not** fixed by this task and are **not** worked around. They are
recorded in `contracts/README.md` and here:

| # | Finding | Impact | Status |
|---|---|---|---|
| 1 | `registerCommitment` had **no access control** | anyone could reserve a `(parcel, season)` commitment id before the farmer does; `registeredId` is permanent | **FIXED** in TASK-004B.2B — a distinct immutable `registrar` role now gates `registerCommitment` |
| 2 | The agreed **reward amount is not bound on-chain** | a funder may fund with 1 wei; the amount is only checked off-chain by `chain_service` | **open** |
| 3 | `settle` **ignores `settleDeadline`** | a verifier can settle after the deadline, when the funder already had the right to refund | **open** |
| 4 | `CommitmentSettled` **omits `evidenceHash`** | the on-chain settlement cannot be linked to the SHA-256 evidence hash from the log alone | **open** |
| 5 | A **zero beneficiary** is accepted | the payout is silently burned | **FIXED** in TASK-004B.2A — `registerCommitment` now rejects `address(0)` with `ZeroBeneficiary()`, and `_payBeneficiary` re-checks before moving ETH |

> Findings 1 and 5 are fixed. Findings 2, 3 and 4 remain open, so the escrow is
> **not production-secure**.

The **registrar** (who may create commitments) and the **verifier** (who may sign
verdicts) are two separate immutable addresses, set at deployment. The trust model,
the MVP assumption and the remaining centralization risk are documented in
[`../contracts/README.md`](../contracts/README.md#the-trust-model).

Two further notes recorded during TASK-004B.1:

- The backend's `build_attestation()` returns the **flat** message, while the
  signer expects `{domain, message}`. The backend therefore cannot call the
  signer as it stands; the domain must be built and wrapped by the caller.
  This is a backend-integration gap and belongs to TASK-004B.2.
- `settle` does not check that `evidenceHash != 0`, unlike the evidence
  registry, which rejects a zero evidence hash.
- The backend's `chain_service._check_register` does not compare `tx["from"]`
  with the on-chain `registrar`, so the off-chain check does not yet mirror the
  on-chain one.

## 9. Files

| File | Role |
|---|---|
| `backend/signer/sign_verdict.mjs` | the signer: JSON on stdin → JSON on stdout |
| `backend/signer/recover_signer.mjs` | independent ethers-based signer recovery |
| `backend/signer/sign_verdict.test.mjs` | 21 focused Node tests for the signer |
| `backend/signer/package.json` | declares `ethers` (v6) |
| `contracts/verify_eip712_signature.py` | the full local interoperability check |
| `tests/test_signer_eip712.py` | 25 cross-language and deployed-contract tests |
