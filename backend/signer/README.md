# TerraCycle EIP-712 verdict signer

A small, dependency-light CLI that produces an EIP-712 signature over a
TerraCycle `VerificationResult`.

## Interface

```text
stdin  : { "domain": {...}, "message": {...} }
stdout : { "signature": "0x…" }        # 65 bytes
stderr : diagnostics
```

The exit status is `0` on success and `1` on any failure. On failure **nothing
is written to stdout**, so a caller can never mistake a failure for a
signature.

```json
{
  "domain": {
    "name": "TerraCycleEscrow",
    "version": "1",
    "chainId": 31337,
    "verifyingContract": "0x5FbDB2315678afecb367f032d93F642f64180aa3"
  },
  "message": {
    "commitmentId": "0x3e92…e871",
    "planHash": "0x161e…5194",
    "evidenceHash": "0x281c…dd75",
    "verdict": 1,
    "validUntil": 1795267533
  }
}
```

## Configuration

| Variable | Meaning |
|---|---|
| `VERIFIER_PRIVATE_KEY` | **required** — the private key of the authorized verifier. Never printed, never logged. |

## Files

| File | Role |
|---|---|
| `sign_verdict.mjs` | the signer |
| `recover_signer.mjs` | recovers the signer of an attestation with ethers, using an **independently declared** copy of the EIP-712 type |
| `sign_verdict.test.mjs` | 21 focused tests (`node --test`) |

## Install and test

```powershell
cd backend\signer
npm install
node --test
```

## Usage

```powershell
$env:VERIFIER_PRIVATE_KEY = "0x…"
Get-Content attestation.json -Raw | node sign_verdict.mjs
```

## Notes

- `ethers` v6 only. `wallet.signTypedData()` is **asynchronous** and the
  result **must be awaited**; without `await` the signer exits 1 with
  "Signer returned an invalid signature" for every valid payload.
- The signer validates the domain (`name`, `version`, `chainId`,
  `verifyingContract`), the five message fields and the verdict range (`0..2`)
  before signing.
- The EIP-712 type definition here must stay identical to the
  `VerificationResult` struct in `contracts/src/TerraCycleEscrow.sol`.
  `recover_signer.mjs` declares its own copy on purpose, so that a drift is
  detected.

Full documentation, the tested workflow and the local interoperability check
are in [`../../docs/eip712-signing.md`](../../docs/eip712-signing.md).
