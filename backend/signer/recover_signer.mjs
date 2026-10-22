#!/usr/bin/env node
/**
 * recover_signer.mjs — independently recover the signer of an EIP-712
 * attestation produced by `sign_verdict.mjs`.
 *
 * This is the verification counterpart of the signer. It deliberately declares
 * its OWN copy of the EIP-712 type definition instead of importing it from
 * `sign_verdict.mjs`, so that a mismatch in the type string, the field order or
 * the field types between the two files is detected rather than hidden.
 *
 * Interface:
 *   stdin  : { "domain": {...}, "message": {...}, "signature": "0x..." }
 *   stdout : { "signer": "0x..." }
 *   stderr : diagnostics; exit status 1 on any failure
 *
 * The private key is NOT needed here and is never read.
 */
import { verifyTypedData } from "ethers";
import { readFileSync } from "node:fs";

// Independent re-declaration of the TerraCycle VerificationResult EIP-712 type.
// Must match contracts/src/TerraCycleEscrow.sol exactly:
//   VerificationResult(bytes32 commitmentId,bytes32 planHash,bytes32 evidenceHash,uint8 verdict,uint64 validUntil)
const VERIFICATION_RESULT_TYPES = {
  VerificationResult: [
    { name: "commitmentId", type: "bytes32" },
    { name: "planHash", type: "bytes32" },
    { name: "evidenceHash", type: "bytes32" },
    { name: "verdict", type: "uint8" },
    { name: "validUntil", type: "uint64" },
  ],
};

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function readStdin() {
  try {
    return readFileSync(0, "utf-8");
  } catch (err) {
    fail(`Failed to read stdin: ${err.message}`);
  }
}

function main() {
  const raw = readStdin();
  if (!raw.trim()) {
    fail("No input provided on stdin");
  }

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (err) {
    fail(`Invalid JSON input: ${err.message}`);
  }

  const { domain, message, signature } = payload;
  if (!domain || !message || !signature) {
    fail("Input must contain 'domain', 'message' and 'signature'");
  }
  if (typeof signature !== "string" || !/^0x[0-9a-fA-F]{130}$/.test(signature)) {
    fail("Signature must be a 65-byte hex string");
  }

  let signer;
  try {
    signer = verifyTypedData(domain, VERIFICATION_RESULT_TYPES, message, signature);
  } catch (err) {
    fail(`Signature recovery failed: ${err.message}`);
  }

  if (typeof signer !== "string" || !/^0x[0-9a-fA-F]{40}$/.test(signer)) {
    fail("Recovered signer is not a valid address");
  }

  process.stdout.write(JSON.stringify({ signer }) + "\n");
}

main();
