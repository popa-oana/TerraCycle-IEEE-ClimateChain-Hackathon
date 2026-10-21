#!/usr/bin/env python
"""
contracts/smoke_test.py — local blockchain smoke test for TerraCycleEvidenceRegistry.

Connects to a LOCAL Anvil node, deploys the registry (or reuses a deployment
address given via REGISTRY_ADDRESS), records ONE evidence entry with clearly
synthetic TEST values, verifies the transaction receipt and the emitted event,
and reads the evidence back from the contract.

This runs against a throwaway local chain only. No real ETH, no public network,
no real wallet credentials. The commitment id and evidence hash used here are
TEST values for this task: they are NOT satellite-derived evidence and they do
NOT describe any agricultural parcel.

Usage:
    cd contracts
    forge build                     # the deployment bytecode comes from the artifact
    anvil --chain-id 31337          # terminal 1
    python smoke_test.py            # terminal 2

Environment:
    ANVIL_RPC_URL          default http://127.0.0.1:8545
    ANVIL_PRIVATE_KEY      deployer private key (Anvil prints it at startup)
    REGISTRY_ADDRESS      optional: reuse an existing local deployment
    REGISTRY_VERIFIER      optional: the authorized verifier (defaults to deployer)

Exit code 0 means every check passed; any failure exits non-zero.
"""

import json
import os
import sys
from pathlib import Path

from eth_abi import decode as abi_decode
from web3 import Web3

CONTRACTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONTRACTS_DIR.parent

ABI_PATH = CONTRACTS_DIR / "abi" / "TerraCycleEvidenceRegistry.json"
ARTIFACT_PATH = CONTRACTS_DIR / "out" / "TerraCycleEvidenceRegistry.sol" / "TerraCycleEvidenceRegistry.json"

EXPECTED_CHAIN_ID = 31337

# Deterministic TEST values. "74657374" is ASCII "test"; these are not hashes of
# any real evidence document.
TEST_COMMITMENT_ID = "0x" + "74657374" + "0" * 54 + "01"
TEST_EVIDENCE_HASH = "0x" + "74657374" + "0" * 54 + "02"
TEST_VERDICT = 0  # conform

EVENT_SIGNATURE = "EvidenceRecorded(bytes32,bytes32,uint8,address,uint256)"

_checks = 0


def check(condition: bool, message: str) -> None:
    global _checks
    _checks += 1
    if condition:
        print(f"  [ok]   {message}")
    else:
        print(f"  [FAIL] {message}")
    if not condition:
        raise AssertionError(message)


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    sys.exit(1)


def to_hex(value) -> str:
    """Normalizes bytes / HexBytes / str to a lowercase 0x-prefixed hex string."""
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    text = str(value)
    return text.lower() if text.startswith("0x") else "0x" + text.lower()


def load_abi() -> list:
    if not ABI_PATH.exists():
        fail(f"ABI not found: {ABI_PATH}")
    return json.loads(ABI_PATH.read_text(encoding="utf-8"))


def load_bytecode() -> str:
    if not ARTIFACT_PATH.exists():
        fail(
            f"Foundry artifact not found: {ARTIFACT_PATH}\n"
            "        Run `forge build` inside contracts/ first."
        )
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    bytecode = artifact["bytecode"]["object"]
    if isinstance(bytecode, dict):  # solc >= 0.8.19 with metadata sources
        bytecode = bytecode.get("object", "")
    if not bytecode:
        fail("Foundry artifact contains no creation bytecode.")
    return bytecode if bytecode.startswith("0x") else "0x" + bytecode


def main() -> int:
    rpc_url = os.environ.get("ANVIL_RPC_URL", "http://127.0.0.1:8545")
    private_key = os.environ.get("ANVIL_PRIVATE_KEY")
    if not private_key:
        fail(
            "ANVIL_PRIVATE_KEY is not set.\n"
            "        Start Anvil and copy one of the development keys it prints\n"
            "        (Anvil default account 0 is the first of them)."
        )
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    print("== TerraCycle evidence registry :: local smoke test ==")
    print(f"RPC URL        : {rpc_url}")

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        fail(f"Cannot reach a chain at {rpc_url}. Is Anvil running?")
    chain_id = w3.eth.chain_id
    block_number = w3.eth.block_number
    check(True, f"connected to a local chain (chain id {chain_id}, block {block_number})")
    check(
        chain_id == EXPECTED_CHAIN_ID,
        f"chain id is the documented local chain id {EXPECTED_CHAIN_ID} (got {chain_id})",
    )

    account = w3.eth.account.from_key(private_key)
    deployer = account.address
    balance = w3.eth.get_balance(deployer)
    check(balance > 0, f"deployer {deployer} holds {balance} wei of local test ETH")

    abi = load_abi()
    verifier = os.environ.get("REGISTRY_VERIFIER", deployer)

    existing_address = os.environ.get("REGISTRY_ADDRESS")
    if existing_address:
        registry_address = Web3.to_checksum_address(existing_address)
        print(f"Registry       : {registry_address} (supplied)")
        check(
            len(w3.eth.get_code(registry_address)) > 0,
            "registry contract code is present at the supplied address",
        )
    else:
        factory = w3.eth.contract(abi=abi, bytecode=load_bytecode())
        deploy_tx = factory.constructor(verifier).build_transaction(
            {"from": deployer, "nonce": w3.eth.get_transaction_count(deployer), "chainId": chain_id}
        )
        signed = w3.eth.account.sign_transaction(deploy_tx, private_key=private_key)
        deploy_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        deploy_receipt = w3.eth.wait_for_transaction_receipt(deploy_hash)
        check(deploy_receipt["status"] == 1, "deployment transaction succeeded")
        registry_address = deploy_receipt["contractAddress"]
        print(f"Registry       : {registry_address}")
        print(f"Deploy tx      : {to_hex(deploy_hash)}")

    registry = w3.eth.contract(address=registry_address, abi=abi)

    on_chain_verifier = registry.functions.verifier().call()
    check(
        on_chain_verifier == Web3.to_checksum_address(verifier),
        f"authorized verifier on chain is {on_chain_verifier}",
    )

    check(
        registry.functions.hasEvidence(TEST_COMMITMENT_ID).call() is False,
        "the test commitment id has no evidence before the transaction",
    )

    print("\n-- recording one evidence entry (TEST values) --")
    record_tx = registry.functions.recordEvidence(
        TEST_COMMITMENT_ID, TEST_EVIDENCE_HASH, TEST_VERDICT
    ).build_transaction(
        {"from": verifier, "nonce": w3.eth.get_transaction_count(verifier), "chainId": chain_id}
    )
    signed = w3.eth.account.sign_transaction(record_tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    tx_hash_hex = to_hex(tx_hash)
    print(f"Tx hash        : {tx_hash_hex}")

    check(receipt["status"] == 1, "evidence transaction status is 1 (successful)")
    check(
        receipt["to"] == registry_address,
        f"transaction targets the registry ({receipt['to']})",
    )
    check(len(receipt["logs"]) == 1, f"exactly one event was emitted ({len(receipt['logs'])})")

    log = receipt["logs"][0]
    check(log["address"] == registry_address, "the event was emitted by the registry")

    expected_topic = to_hex(Web3.keccak(text=EVENT_SIGNATURE))
    check(to_hex(log["topics"][0]) == expected_topic, f"event signature is {EVENT_SIGNATURE}")
    check(
        to_hex(log["topics"][1]) == to_hex(TEST_COMMITMENT_ID),
        "event carries the submitted commitment id",
    )
    check(
        to_hex(log["topics"][2]) == to_hex(TEST_EVIDENCE_HASH),
        "event carries the submitted evidence hash",
    )
    check(
        int(to_hex(log["topics"][3]), 16) == TEST_VERDICT,
        f"event carries verdict {TEST_VERDICT}",
    )
    recorder, recorded_at = abi_decode(["address", "uint256"], bytes(log["data"]))
    check(
        Web3.to_checksum_address(recorder) == Web3.to_checksum_address(verifier),
        f"event records the authorized verifier as recorder ({recorder})",
    )
    check(recorded_at > 0, f"event records a block timestamp ({recorded_at})")

    print("\n-- reading the evidence back from the contract --")
    stored = registry.functions.getEvidence(TEST_COMMITMENT_ID).call()
    stored_commitment_id, stored_evidence_hash, stored_verdict, stored_recorded_at, stored_recorder = stored
    check(
        to_hex(stored_commitment_id) == to_hex(TEST_COMMITMENT_ID),
        f"stored commitment id matches ({to_hex(stored_commitment_id)})",
    )
    check(
        to_hex(stored_evidence_hash) == to_hex(TEST_EVIDENCE_HASH),
        f"stored evidence hash matches ({to_hex(stored_evidence_hash)})",
    )
    check(stored_verdict == TEST_VERDICT, f"stored verdict matches ({stored_verdict})")
    check(
        Web3.to_checksum_address(stored_recorder) == Web3.to_checksum_address(verifier),
        f"stored recorder matches ({stored_recorder})",
    )
    check(
        registry.functions.hasEvidence(TEST_COMMITMENT_ID).call() is True,
        "hasEvidence() reports the commitment id as recorded",
    )

    print(f"\nALL {_checks} CHECKS PASSED")
    print(f"registry address : {registry_address}")
    print(f"evidence tx hash : {tx_hash_hex}")
    print("note: the recorded values are TEST values, not satellite-derived evidence")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"\nSMOKE TEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - the script must fail loudly
        print(f"\nSMOKE TEST ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
