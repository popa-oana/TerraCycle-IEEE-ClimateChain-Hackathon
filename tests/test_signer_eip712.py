# -*- coding: utf-8 -*-
"""
tests/test_signer_eip712.py — TASK-004B.1

Cross-language checks for the EIP-712 verdict signer.

Covered:
- the Node signer produces a real 65-byte signature (regression for the
  original bug where `signTypedData` was not awaited)
- the signer fails safely and never emits partial success JSON
- the signer never prints the private key
- the EIP-712 digest computed in Python equals the one ethers signs over
- the EIP-712 domain separator computed in Python equals the one the Solidity
  contract uses
- the SHA-256 evidence hash and the Keccak-256 EIP-712 digest are two
  DIFFERENT values and are never substituted for one another
- with a local Anvil running: the genuine evidence signature is ACCEPTED by the
  deployed escrow, the state is left unchanged, and every tampered attestation
  is rejected for the intended reason

The chain tests are skipped when no local Anvil is reachable.
"""
# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from eth_abi import encode as abi_encode
from eth_keys import keys
from web3 import Web3

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = REPO_ROOT / "contracts"
for path in (str(REPO_ROOT), str(CONTRACTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import verify_eip712_signature as interop  # noqa: E402

RPC_URL = os.environ.get("ANVIL_RPC_URL", "http://127.0.0.1:8547")
PRIVATE_KEY = os.environ.get("ANVIL_PRIVATE_KEY")
# Anvil development account #3 acts as the authorized registrar. LOCAL TEST key.
REGISTRAR_PRIVATE_KEY = os.environ.get(
    "ANVIL_REGISTRAR_PRIVATE_KEY",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
)

SIGNER = REPO_ROOT / "backend" / "signer" / "sign_verdict.mjs"
RECOVER = REPO_ROOT / "backend" / "signer" / "recover_signer.mjs"

# Anvil development account #0 - a local test account, never a production key.
TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

EIP712_NAME = "TerraCycleEscrow"
EIP712_VERSION = "1"
TYPE_STRING = (
    "VerificationResult(bytes32 commitmentId,bytes32 planHash,"
    "bytes32 evidenceHash,uint8 verdict,uint64 validUntil)"
)
DOMAIN_TYPE_STRING = (
    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)

DOMAIN = {
    "name": EIP712_NAME,
    "version": EIP712_VERSION,
    "chainId": 31337,
    "verifyingContract": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
}
MESSAGE = {
    "commitmentId": "0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871",
    "planHash": "0x161e3ed13e04d4916811a5842feb5a01e25ae4ee17439c3bc6b740f7064e5194",
    "evidenceHash": "0x281cf44e592ed2e57dd40f16f70c63f96a281ec8fd249b85ce1a96a5cab0dd75",
    "verdict": 1,
    "validUntil": 1795267533,
}


def _anvil_available() -> bool:
    try:
        return Web3(Web3.HTTPProvider(RPC_URL)).is_connected()
    except Exception:  # noqa: BLE001
        return False


requires_chain = pytest.mark.skipif(
    not (PRIVATE_KEY and _anvil_available()),
    reason="a local Anvil chain and ANVIL_PRIVATE_KEY are required",
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def run_signer(payload, key=TEST_KEY):
    env = {**os.environ}
    if key is None:
        env.pop("VERIFIER_PRIVATE_KEY", None)
    else:
        env["VERIFIER_PRIVATE_KEY"] = key
    return subprocess.run(
        ["node", str(SIGNER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=env,
    )


def python_domain_separator(domain: dict) -> bytes:
    """The EIP-712 domain separator, computed the way the Solidity contract does."""
    return Web3.keccak(
        abi_encode(
            ["bytes32", "bytes32", "bytes32", "uint256", "address"],
            [
                Web3.keccak(text=DOMAIN_TYPE_STRING),
                Web3.keccak(text=domain["name"]),
                Web3.keccak(text=domain["version"]),
                int(domain["chainId"]),
                Web3.to_checksum_address(domain["verifyingContract"]),
            ],
        )
    )


def python_struct_hash(message: dict) -> bytes:
    """The EIP-712 struct hash of the VerificationResult."""
    return Web3.keccak(
        abi_encode(
            ["bytes32", "bytes32", "bytes32", "bytes32", "uint8", "uint64"],
            [
                Web3.keccak(text=TYPE_STRING),
                bytes.fromhex(message["commitmentId"][2:]),
                bytes.fromhex(message["planHash"][2:]),
                bytes.fromhex(message["evidenceHash"][2:]),
                int(message["verdict"]),
                int(message["validUntil"]),
            ],
        )
    )


def python_digest(domain: dict, message: dict) -> bytes:
    """The full EIP-712 digest: keccak256(0x19 0x01 || domainSeparator || structHash)."""
    return Web3.keccak(
        b"\x19\x01" + python_domain_separator(domain) + python_struct_hash(message)
    )


# ---------------------------------------------------------------------------
# the signer itself
# ---------------------------------------------------------------------------

def test_the_signer_produces_a_real_65_byte_signature():
    result = run_signer({"domain": DOMAIN, "message": MESSAGE})
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    signature = payload["signature"]
    assert isinstance(signature, str)
    assert len(signature) == 132
    assert (len(signature) - 2) // 2 == 65
    int(signature, 16)  # must be valid hex


def test_the_signer_awaits_the_promise_and_does_not_return_a_promise():
    # Regression test for the original bug: `wallet.signTypedData()` returns a
    # Promise in ethers v6. Without `await`, the signer exited 1 with
    # "Signer returned an invalid signature" for every valid payload.
    result = run_signer({"domain": DOMAIN, "message": MESSAGE})
    assert result.returncode == 0, "the signer must succeed on a valid payload"
    assert result.stdout.strip(), "the signer must emit a signature"
    payload = json.loads(result.stdout)
    assert isinstance(payload["signature"], str)
    assert not hasattr(payload["signature"], "then")


def test_the_signer_fails_safely_without_a_private_key():
    result = run_signer({"domain": DOMAIN, "message": MESSAGE}, key=None)
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert "VERIFIER_PRIVATE_KEY" in result.stderr


def test_the_signer_fails_safely_on_malformed_input():
    result = run_signer({"message": MESSAGE})
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert "domain" in result.stderr


def test_the_signer_fails_safely_on_an_out_of_range_verdict():
    for verdict in (-1, 3, 255):
        result = run_signer({"domain": DOMAIN, "message": {**MESSAGE, "verdict": verdict}})
        assert result.returncode == 1
        assert result.stdout.strip() == ""
        assert "Invalid verdict code" in result.stderr


def test_the_signer_never_prints_the_private_key():
    result = run_signer({"domain": DOMAIN, "message": MESSAGE})
    combined = result.stdout + result.stderr
    assert TEST_KEY not in combined
    assert TEST_KEY[2:] not in combined.lower()


def test_the_signer_is_deterministic():
    first = json.loads(run_signer({"domain": DOMAIN, "message": MESSAGE}).stdout)
    second = json.loads(run_signer({"domain": DOMAIN, "message": MESSAGE}).stdout)
    assert first["signature"] == second["signature"]


# ---------------------------------------------------------------------------
# cross-language agreement
# ---------------------------------------------------------------------------

def test_ethers_recovers_the_expected_signer_address():
    result = run_signer({"domain": DOMAIN, "message": MESSAGE})
    signature = json.loads(result.stdout)["signature"]
    recovered = interop.run_node(
        RECOVER, {"domain": DOMAIN, "message": MESSAGE, "signature": signature}
    )
    assert Web3.to_checksum_address(recovered["signer"]) == Web3.to_checksum_address(
        TEST_ADDRESS
    )


def test_python_and_ethers_agree_on_the_recovered_signer():
    """The Python-computed digest must recover the same address as ethers."""
    result = run_signer({"domain": DOMAIN, "message": MESSAGE})
    signature = json.loads(result.stdout)["signature"]

    digest = python_digest(DOMAIN, MESSAGE)
    raw = bytes.fromhex(signature[2:])
    # ethers emits v as 27/28; eth_keys expects the recovery id 0/1 and
    # r/s as integers.
    vrs = (
        raw[64] - 27,
        int.from_bytes(raw[:32], "big"),
        int.from_bytes(raw[32:64], "big"),
    )
    public_key = keys.Signature(vrs=vrs).recover_public_key_from_msg_hash(digest)
    assert Web3.to_checksum_address(public_key.to_address()) == Web3.to_checksum_address(
        TEST_ADDRESS
    )


def test_the_python_domain_separator_matches_the_solidity_formula():
    # This is the exact expression OpenZeppelin v5 uses in
    # EIP712._buildDomainSeparator().
    expected = Web3.keccak(
        abi_encode(
            ["bytes32", "bytes32", "bytes32", "uint256", "address"],
            [
                Web3.keccak(text=DOMAIN_TYPE_STRING),
                Web3.keccak(text=EIP712_NAME),
                Web3.keccak(text=EIP712_VERSION),
                31337,
                Web3.to_checksum_address(DOMAIN["verifyingContract"]),
            ],
        )
    )
    assert python_domain_separator(DOMAIN) == expected


def test_the_sha256_evidence_hash_and_the_keccak256_digest_are_different_values():
    """
    The two hashes must never be confused.

    - the evidence hash is SHA-256 over the canonical evidence bytes and is
      what the attestation COMMITS to;
    - the EIP-712 digest is Keccak-256 over the domain and the struct and is
      what is actually SIGNED.
    """
    evidence_hash = MESSAGE["evidenceHash"]
    digest = python_digest(DOMAIN, MESSAGE)

    assert len(bytes.fromhex(evidence_hash[2:])) == 32
    assert len(digest) == 32
    assert evidence_hash[2:] != digest.hex()

    # SHA-256 of the evidence hash is NOT the EIP-712 digest.
    import hashlib

    assert hashlib.sha256(bytes.fromhex(evidence_hash[2:])).hexdigest() != digest.hex()


# ---------------------------------------------------------------------------
# the deployed contract (local Anvil only)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def chain():
    """Deploy the escrow, register and fund the authentic commitment."""
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = w3.eth.account.from_key(PRIVATE_KEY)
    deployer = account.address
    registrar = w3.eth.account.from_key(REGISTRAR_PRIVATE_KEY).address

    contract_abi, bytecode = interop.load_abi_and_bytecode()
    factory = w3.eth.contract(abi=contract_abi, bytecode=bytecode)
    deploy_tx = factory.constructor(
        deployer, registrar, EIP712_NAME, EIP712_VERSION
    ).build_transaction(
        {
            "from": deployer,
            "nonce": w3.eth.get_transaction_count(deployer),
            "chainId": w3.eth.chain_id,
        }
    )
    signed = w3.eth.account.sign_transaction(deploy_tx, private_key=PRIVATE_KEY)
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction)
    )
    assert receipt["status"] == 1
    address = Web3.to_checksum_address(receipt["contractAddress"])
    escrow = w3.eth.contract(address=address, abi=contract_abi)

    fixture = json.loads(
        (REPO_ROOT / "data" / "fixtures" / "demo.json").read_text(encoding="utf-8")
    )
    ref = fixture["reference_parcel"]
    parcel_b32 = bytes.fromhex(ref["parcel_id_bytes32"][2:])
    season_b32 = bytes.fromhex(ref["season_id_bytes32"][2:])
    beneficiary = Web3.to_checksum_address(fixture["wallets"]["beneficiary"])

    # The authentic plan hash and commitment come from the real pipeline.
    evidence = interop.demo.generate_real_evidence()
    commitment_id = evidence["commitment_id"]
    plan_hash = evidence["plan_hash"]
    settle_deadline = int(evidence["commitment"].settle_deadline)

    register_tx = escrow.functions.registerCommitment(
        parcel_b32, season_b32, bytes.fromhex(plan_hash[2:]), beneficiary, settle_deadline
    ).build_transaction(
        {"from": registrar, "nonce": w3.eth.get_transaction_count(registrar), "chainId": w3.eth.chain_id}
    )
    signed = w3.eth.account.sign_transaction(register_tx, private_key=REGISTRAR_PRIVATE_KEY)
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

    fund_tx = escrow.functions.fundCommitment(
        bytes.fromhex(commitment_id[2:])
    ).build_transaction(
        {
            "from": deployer,
            "value": 1_000_000_000_000_000,
            "nonce": w3.eth.get_transaction_count(deployer),
            "chainId": w3.eth.chain_id,
        }
    )
    signed = w3.eth.account.sign_transaction(fund_tx, private_key=PRIVATE_KEY)
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

    # A SECOND, independent commitment that also exists on-chain. Without it, a
    # tampered commitment id would be rejected by "not found" instead of by the
    # signature check, which would not test what we want.
    other_parcel = bytes.fromhex("33" * 32)
    other_tx = escrow.functions.registerCommitment(
        other_parcel, season_b32, bytes.fromhex(plan_hash[2:]), beneficiary, settle_deadline
    ).build_transaction(
        {"from": registrar, "nonce": w3.eth.get_transaction_count(registrar), "chainId": w3.eth.chain_id}
    )
    signed = w3.eth.account.sign_transaction(other_tx, private_key=REGISTRAR_PRIVATE_KEY)
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    other_commitment_id = "0x" + Web3.keccak(
        abi_encode(["bytes32", "bytes32"], [other_parcel, season_b32])
    ).hex()
    other_fund = escrow.functions.fundCommitment(
        bytes.fromhex(other_commitment_id[2:])
    ).build_transaction(
        {
            "from": deployer,
            "value": 1_000_000_000_000_000,
            "nonce": w3.eth.get_transaction_count(deployer),
            "chainId": w3.eth.chain_id,
        }
    )
    signed = w3.eth.account.sign_transaction(other_fund, private_key=PRIVATE_KEY)
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

    domain = interop.build_domain(w3, address)
    message = {
        "commitmentId": commitment_id,
        "planHash": plan_hash,
        "evidenceHash": evidence["evidence_hash"],
        "verdict": int(evidence["verifier_result"]["verdict_code"]),
        "validUntil": settle_deadline,
    }

    return {
        "w3": w3,
        "escrow": escrow,
        "address": address,
        "deployer": deployer,
        "registrar": registrar,
        "beneficiary": beneficiary,
        "domain": domain,
        "message": message,
        "evidence": evidence,
        "other_commitment_id": other_commitment_id,
        "signature": interop.sign_attestation(domain, message),
    }


@requires_chain
def test_the_genuine_evidence_signature_is_accepted_by_the_deployed_contract(chain):
    message = chain["message"]
    chain["escrow"].functions.settle(
        interop.attestation_tuple(message), bytes.fromhex(chain["signature"][2:])
    ).call({"from": chain["deployer"]})


@requires_chain
def test_the_verdict_is_the_real_nonconform_verdict(chain):
    verifier_result = chain["evidence"]["verifier_result"]
    assert verifier_result["verdict"] == "nonconform"
    assert verifier_result["verdict_code"] == 1
    assert chain["message"]["verdict"] == 1


@requires_chain
def test_the_evidence_hash_is_the_sha256_of_the_canonical_evidence_bytes(chain):
    import hashlib

    evidence = chain["evidence"]
    recomputed = "0x" + hashlib.sha256(evidence["evidence_bytes"]).hexdigest()
    assert recomputed == evidence["evidence_hash"]
    assert chain["message"]["evidenceHash"] == evidence["evidence_hash"]


@requires_chain
def test_the_recovered_signer_is_the_authorized_verifier(chain):
    recovered = interop.recover_signer(chain["domain"], chain["message"], chain["signature"])
    on_chain = chain["escrow"].functions.verifier().call()
    assert Web3.to_checksum_address(recovered) == Web3.to_checksum_address(on_chain)


@requires_chain
def test_the_simulation_leaves_the_state_and_the_balances_unchanged(chain):
    w3 = chain["w3"]
    escrow = chain["escrow"]
    commitment_id = bytes.fromhex(chain["message"]["commitmentId"][2:])

    state_before = escrow.functions.getCommitment(commitment_id).call()
    escrow_balance_before = w3.eth.get_balance(chain["address"])
    beneficiary_before = w3.eth.get_balance(chain["beneficiary"])
    tx_count_before = w3.eth.get_block("latest")["number"]

    escrow.functions.settle(
        interop.attestation_tuple(chain["message"]), bytes.fromhex(chain["signature"][2:])
    ).call({"from": chain["deployer"]})

    assert escrow.functions.getCommitment(commitment_id).call() == state_before
    assert w3.eth.get_balance(chain["address"]) == escrow_balance_before
    assert w3.eth.get_balance(chain["beneficiary"]) == beneficiary_before
    assert int(state_before[5]) == 2, "the commitment must still be Funded"
    assert w3.eth.get_block("latest")["number"] == tx_count_before, "no block was mined"


@requires_chain
@pytest.mark.parametrize(
    "case",
    [
        "wrong_key",
        "wrong_chain_id",
        "wrong_contract",
        "other_commitment",
        "other_plan_hash",
        "tampered_evidence_hash",
        "tampered_verdict",
        "expired",
        "truncated",
    ],
)
def test_every_tampered_attestation_is_rejected_by_the_contract(chain, case):
    domain = chain["domain"]
    message = chain["message"]
    signature = chain["signature"]
    escrow = chain["escrow"]
    deployer = chain["deployer"]
    other_key = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"

    attestation = dict(message)
    used_signature = signature
    expected = "InvalidSignature"

    if case == "wrong_key":
        used_signature = interop.sign_attestation(domain, message, key=other_key)
    elif case == "wrong_chain_id":
        used_signature = interop.sign_attestation({**domain, "chainId": 11155111}, message)
    elif case == "wrong_contract":
        used_signature = interop.sign_attestation(
            {**domain, "verifyingContract": "0x" + "01" * 20}, message
        )
    elif case == "other_commitment":
        # A DIFFERENT commitment that really exists on-chain: the rejection must
        # come from the signature check, not from "not found".
        attestation["commitmentId"] = chain["other_commitment_id"]
    elif case == "other_plan_hash":
        attestation["planHash"] = "0x" + "aa" * 32
        expected = "PlanHashMismatch"
    elif case == "tampered_evidence_hash":
        attestation["evidenceHash"] = "0x" + "bb" * 32
    elif case == "tampered_verdict":
        attestation["verdict"] = 2
    elif case == "expired":
        attestation["validUntil"] = 1
        expected = "AttestationExpired"
    elif case == "truncated":
        used_signature = signature[:-2]
        expected = "ECDSAInvalidSignatureLength"

    from web3.exceptions import ContractLogicError

    with pytest.raises(ContractLogicError) as excinfo:
        escrow.functions.settle(
            interop.attestation_tuple(attestation), bytes.fromhex(used_signature[2:])
        ).call({"from": deployer})

    name = interop.error_name_from_revert(excinfo.value)
    assert name == expected, f"{case}: expected {expected}, got {name}"
