/**
 * sign_verdict.test.mjs — focused tests for the TerraCycle EIP-712 signer.
 *
 * Run with:
 *     node --test backend/signer/
 *
 * These tests drive the signer exactly the way the backend does: as a
 * subprocess that receives a JSON payload on stdin and must answer with a JSON
 * object on stdout. The private key used here is the well-known Anvil
 * development key (a local test account, never a production key).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { Wallet, verifyTypedData, computeAddress } from "ethers";

const HERE = dirname(fileURLToPath(import.meta.url));
const SIGNER = join(HERE, "sign_verdict.mjs");
const RECOVER = join(HERE, "recover_signer.mjs");

// Anvil development account #0 — a local test account.
const TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";
const TEST_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";

const TYPES = {
  VerificationResult: [
    { name: "commitmentId", type: "bytes32" },
    { name: "planHash", type: "bytes32" },
    { name: "evidenceHash", type: "bytes32" },
    { name: "verdict", type: "uint8" },
    { name: "validUntil", type: "uint64" },
  ],
};

const DOMAIN = {
  name: "TerraCycleEscrow",
  version: "1",
  chainId: 31337,
  verifyingContract: "0x5FbDB2315678afecb367f032d93F642f64180aa3",
};

const MESSAGE = {
  commitmentId: "0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871",
  planHash: "0x161e3ed13e04d4916811a5842feb5a01e25ae4ee17439c3bc6b740f7064e5194",
  evidenceHash: "0x281cf44e592ed2e57dd40f16f70c63f96a281ec8fd249b85ce1a96a5cab0dd75",
  verdict: 1,
  validUntil: 1795267533,
};

function run(script, payload, { key = TEST_KEY } = {}) {
  const env = { ...process.env };
  if (key === null) {
    delete env.VERIFIER_PRIVATE_KEY;
  } else {
    env.VERIFIER_PRIVATE_KEY = key;
  }
  const result = spawnSync(process.execPath, [script], {
    input: typeof payload === "string" ? payload : JSON.stringify(payload),
    encoding: "utf-8",
    env,
  });
  return {
    status: result.status,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

// ---------------------------------------------------------------------------
// happy path
// ---------------------------------------------------------------------------

test("signs a valid attestation and exits 0", () => {
  const r = run(SIGNER, { domain: DOMAIN, message: MESSAGE });
  assert.equal(r.status, 0, `stderr: ${r.stderr}`);
  const out = JSON.parse(r.stdout);
  assert.match(out.signature, /^0x[0-9a-f]{130}$/);
  assert.equal((out.signature.length - 2) / 2, 65);
});

test("the signer awaits the promise and returns a real string, not a Promise", () => {
  // This is the regression test for the original bug: without `await`,
  // `signTypedData` yields a Promise and the signer exits 1 with
  // "Signer returned an invalid signature".
  const r = run(SIGNER, { domain: DOMAIN, message: MESSAGE });
  assert.equal(r.status, 0, "the signer must not fail on a valid payload");
  assert.notEqual(r.stdout.trim(), "", "the signer must emit a signature");
  const parsed = JSON.parse(r.stdout);
  assert.equal(typeof parsed.signature, "string");
  assert.equal(typeof parsed.signature.then, "undefined", "signature must not be a Promise");
});

test("the signature recovers to the signing address", () => {
  const r = run(SIGNER, { domain: DOMAIN, message: MESSAGE });
  const { signature } = JSON.parse(r.stdout);
  const signer = verifyTypedData(DOMAIN, TYPES, MESSAGE, signature);
  assert.equal(signer.toLowerCase(), TEST_ADDRESS.toLowerCase());
});

test("recover_signer.mjs recovers the same address independently", () => {
  const signed = run(SIGNER, { domain: DOMAIN, message: MESSAGE });
  const { signature } = JSON.parse(signed.stdout);
  const recovered = run(RECOVER, { domain: DOMAIN, message: MESSAGE, signature });
  assert.equal(recovered.status, 0, `stderr: ${recovered.stderr}`);
  const { signer } = JSON.parse(recovered.stdout);
  assert.equal(signer.toLowerCase(), TEST_ADDRESS.toLowerCase());
});

test("signing is deterministic for identical input", () => {
  const a = JSON.parse(run(SIGNER, { domain: DOMAIN, message: MESSAGE }).stdout);
  const b = JSON.parse(run(SIGNER, { domain: DOMAIN, message: MESSAGE }).stdout);
  assert.equal(a.signature, b.signature);
});

test("a different message produces a different signature", () => {
  const a = JSON.parse(run(SIGNER, { domain: DOMAIN, message: MESSAGE }).stdout);
  const other = { ...MESSAGE, verdict: 2 };
  const b = JSON.parse(run(SIGNER, { domain: DOMAIN, message: other }).stdout);
  assert.notEqual(a.signature, b.signature);
});

test("the signature does not verify against a different chain id", () => {
  // A well-formed ECDSA signature over a different digest does not "fail to
  // recover": it recovers a DIFFERENT address. This mirrors the contract,
  // which compares the recovered signer against the authorized verifier and
  // rejects on mismatch (InvalidSignature).
  const { signature } = JSON.parse(run(SIGNER, { domain: DOMAIN, message: MESSAGE }).stdout);
  const wrong = { ...DOMAIN, chainId: 11155111 };
  const recovered = verifyTypedData(wrong, TYPES, MESSAGE, signature);
  assert.notEqual(recovered.toLowerCase(), TEST_ADDRESS.toLowerCase());
});

test("the signature does not verify against a different contract address", () => {
  const { signature } = JSON.parse(run(SIGNER, { domain: DOMAIN, message: MESSAGE }).stdout);
  const wrong = { ...DOMAIN, verifyingContract: "0x0000000000000000000000000000000000000001" };
  const recovered = verifyTypedData(wrong, TYPES, MESSAGE, signature);
  assert.notEqual(recovered.toLowerCase(), TEST_ADDRESS.toLowerCase());
});

test("the signature does not verify for a modified evidence hash", () => {
  const { signature } = JSON.parse(run(SIGNER, { domain: DOMAIN, message: MESSAGE }).stdout);
  const tampered = { ...MESSAGE, evidenceHash: "0x" + "11".repeat(32) };
  const recovered = verifyTypedData(DOMAIN, TYPES, tampered, signature);
  assert.notEqual(recovered.toLowerCase(), TEST_ADDRESS.toLowerCase());
});

// ---------------------------------------------------------------------------
// failure paths
// ---------------------------------------------------------------------------

test("fails safely when VERIFIER_PRIVATE_KEY is missing", () => {
  const r = run(SIGNER, { domain: DOMAIN, message: MESSAGE }, { key: null });
  assert.equal(r.status, 1);
  assert.equal(r.stdout.trim(), "", "no partial success JSON on failure");
  assert.match(r.stderr, /VERIFIER_PRIVATE_KEY/);
});

test("fails safely when the private key is invalid", () => {
  const r = run(SIGNER, { domain: DOMAIN, message: MESSAGE }, { key: "0xnothex" });
  assert.equal(r.status, 1);
  assert.equal(r.stdout.trim(), "");
  assert.match(r.stderr, /Invalid private key/);
});

test("fails safely on empty stdin", () => {
  const r = run(SIGNER, "");
  assert.equal(r.status, 1);
  assert.equal(r.stdout.trim(), "");
  assert.match(r.stderr, /No input provided/);
});

test("fails safely on malformed JSON", () => {
  const r = run(SIGNER, "{not json");
  assert.equal(r.status, 1);
  assert.equal(r.stdout.trim(), "");
  assert.match(r.stderr, /Invalid JSON input/);
});

test("fails safely when domain or message is missing", () => {
  const r = run(SIGNER, { message: MESSAGE });
  assert.equal(r.status, 1);
  assert.equal(r.stdout.trim(), "");
  assert.match(r.stderr, /domain.*message|message.*domain/i);
});

test("fails safely when a required message field is missing", () => {
  const { evidenceHash, ...incomplete } = MESSAGE;
  const r = run(SIGNER, { domain: DOMAIN, message: incomplete });
  assert.equal(r.status, 1);
  assert.equal(r.stdout.trim(), "");
  assert.match(r.stderr, /evidenceHash/);
});

test("fails safely on an out-of-range verdict", () => {
  for (const verdict of [-1, 3, 255]) {
    const r = run(SIGNER, { domain: DOMAIN, message: { ...MESSAGE, verdict } });
    assert.equal(r.status, 1, `verdict ${verdict} must be rejected`);
    assert.equal(r.stdout.trim(), "");
    assert.match(r.stderr, /Invalid verdict code/);
  }
});

test("fails safely when the domain is incomplete", () => {
  const r = run(SIGNER, { domain: { name: "TerraCycleEscrow" }, message: MESSAGE });
  assert.equal(r.status, 1);
  assert.equal(r.stdout.trim(), "");
  assert.match(r.stderr, /Domain must contain/);
});

test("fails safely when ethers itself refuses to sign", () => {
  // An invalid chain id makes ethers throw inside signTypedData.
  const r = run(SIGNER, {
    domain: { ...DOMAIN, chainId: "not-a-number" },
    message: MESSAGE,
  });
  assert.equal(r.status, 1);
  assert.equal(r.stdout.trim(), "", "no partial success JSON on failure");
  assert.ok(r.stderr.length > 0);
});

test("never prints the private key", () => {
  const r = run(SIGNER, { domain: DOMAIN, message: MESSAGE });
  const combined = r.stdout + r.stderr;
  assert.ok(!combined.includes(TEST_KEY), "the private key must never be printed");
  assert.ok(!combined.toLowerCase().includes(TEST_KEY.slice(2).toLowerCase()));
  // and the account's address is not the secret
  assert.ok(!combined.includes(TEST_KEY));
});

test("recover_signer.mjs rejects a malformed signature", () => {
  const r = run(RECOVER, { domain: DOMAIN, message: MESSAGE, signature: "0xdeadbeef" });
  assert.equal(r.status, 1);
  assert.equal(r.stdout.trim(), "");
});

test("recover_signer.mjs rejects a signature made by a different key", async () => {
  const otherKey = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d";
  const otherWallet = new Wallet(otherKey);
  const signature = await otherWallet.signTypedData(DOMAIN, TYPES, MESSAGE);
  const r = run(RECOVER, { domain: DOMAIN, message: MESSAGE, signature });
  assert.equal(r.status, 0, `stderr: ${r.stderr}`);
  const { signer } = JSON.parse(r.stdout);
  assert.equal(signer.toLowerCase(), computeAddress(otherKey).toLowerCase());
  assert.notEqual(signer.toLowerCase(), TEST_ADDRESS.toLowerCase());
});
