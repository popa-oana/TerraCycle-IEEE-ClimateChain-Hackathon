import { Wallet } from "ethers";
import { readFileSync } from "node:fs";

const VERIFICATION_RESULT_TYPES = {
  VerificationResult: [
    { name: "commitmentId", type: "bytes32" },
    { name: "planHash", type: "bytes32" },
    { name: "evidenceHash", type: "bytes32" },
    { name: "verdict", type: "uint8" },
    { name: "validUntil", type: "uint64" },
  ],
};

function readStdin() {
  try {
    return readFileSync(0, "utf-8");
  } catch (err) {
    process.stderr.write(`Failed to read stdin: ${err.message}\n`);
    process.exit(1);
  }
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function main() {
  const privateKey = process.env.VERIFIER_PRIVATE_KEY;
  if (!privateKey) {
    fail("VERIFIER_PRIVATE_KEY is not set");
  }

  const rawInput = readStdin();
  if (!rawInput.trim()) {
    fail("No input provided on stdin");
  }

  let payload;
  try {
    payload = JSON.parse(rawInput);
  } catch (err) {
    fail(`Invalid JSON input: ${err.message}`);
  }

  const { domain, message } = payload;
  if (!domain || !message) {
    fail("Input must contain 'domain' and 'message' objects");
  }

  if (!domain.name || !domain.version || domain.chainId === undefined || !domain.verifyingContract) {
    fail("Domain must contain name, version, chainId and verifyingContract");
  }

  const requiredMessageFields = ["commitmentId", "planHash", "evidenceHash", "verdict", "validUntil"];
  const missing = requiredMessageFields.filter((field) => !(field in message));
  if (missing.length > 0) {
    fail(`Message is missing required fields: ${missing.join(", ")}`);
  }

  if (!Number.isInteger(message.verdict) || message.verdict < 0 || message.verdict > 2) {
    fail(`Invalid verdict code: ${message.verdict}`);
  }

  let wallet;
  try {
    wallet = new Wallet(privateKey);
  } catch (err) {
    fail(`Invalid private key: ${err.message}`);
  }

  let signature;
  try {
    signature = wallet.signTypedData(domain, VERIFICATION_RESULT_TYPES, message);
  } catch (err) {
    fail(`Signing failed: ${err.message}`);
  }

  if (typeof signature !== "string" || !signature.startsWith("0x") || signature.length !== 132) {
    fail("Signer returned an invalid signature");
  }

  process.stdout.write(JSON.stringify({ signature }) + "\n");
}

main();
