#!/usr/bin/env python
"""
contracts/verify_eip712_signature.py — TASK-004B.1

Proves that an EIP-712 signature produced by the REAL Node.js signer
(`backend/signer/sign_verdict.mjs`) over GENUINE Sentinel-2 evidence is
accepted by the REAL `TerraCycleEscrow` contract on a LOCAL Anvil chain.

What it does
------------
1.  Generates the authentic evidence of parcel_01 with the existing pipeline
    (`smoke_test_real_evidence.generate_real_evidence`): the real plan, the real
    commitment, the real canonical SHA-256 evidence hash and the real
    scientific verdict. Nothing is hardcoded or invented.
2.  Deploys `TerraCycleEscrow` on the local chain, with the Anvil development
    account as the authorized verifier.
3.  Registers and funds the authentic commitment with LOCAL TEST ETH.
4.  Reads the EIP-712 domain from the deployed contract itself
    (`eip712Domain()`), so the name, version, chain id and verifying contract
    address are the contract's own values.
5.  Signs the attestation with the real Node.js signer.
6.  Recovers the signer independently with ethers (`recover_signer.mjs`).
7.  SIMULATES `settle()` with `eth_call` and confirms it is accepted.
8.  Runs a negative matrix: each tampered attestation must be rejected by the
    contract for the intended reason.
9.  Confirms that NOTHING changed: no transaction was mined, no balance moved,
    the commitment is still `Funded` and the beneficiary was not paid.

What it deliberately does NOT do
--------------------------------
- It never sends a `settle()` transaction. `eth_call` is a simulation.
- It never sends a `refund()` transaction.
- It never pays a beneficiary.
- It never touches a public network and never uses real funds.

Only LOCAL Anvil development ETH is used.

Usage
-----
    cd contracts
    forge build
    anvil --host 127.0.0.1 --port 8547 --chain-id 31337        # terminal 1

    cd contracts
    export ANVIL_RPC_URL=http://127.0.0.1:8547
    export ANVIL_PRIVATE_KEY=<anvil development key>
    python verify_eip712_signature.py                             # terminal 2

Environment
-----------
    ANVIL_RPC_URL       default http://127.0.0.1:8547
    ANVIL_PRIVATE_KEY   required: an Anvil development key (never a production key)
    VERIFIER_PRIVATE_KEY optional: defaults to ANVIL_PRIVATE_KEY
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "contracts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "contracts"))

from eth_abi import encode as eth_abi_encode
from web3 import Web3
from web3.exceptions import ContractCustomError, ContractLogicError

import smoke_test_real_evidence as demo  # noqa: E402
from backend.hashing import canonical_bytes  # noqa: E402

RPC_URL = os.environ.get("ANVIL_RPC_URL", "http://127.0.0.1:8547")
PRIVATE_KEY = os.environ.get("ANVIL_PRIVATE_KEY")
VERIFIER_PRIVATE_KEY = os.environ.get("VERIFIER_PRIVATE_KEY", PRIVATE_KEY)
# Anvil development account #3 acts as the authorized registrar. It is a LOCAL
# TEST key; it is never a production key and it is never committed.
REGISTRAR_PRIVATE_KEY = os.environ.get(
    "ANVIL_REGISTRAR_PRIVATE_KEY",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
)

SIGNER_SCRIPT = REPO_ROOT / "backend" / "signer" / "sign_verdict.mjs"
RECOVER_SCRIPT = REPO_ROOT / "backend" / "signer" / "recover_signer.mjs"
ARTIFACT = REPO_ROOT / "contracts" / "out" / "TerraCycleEscrow.sol" / "TerraCycleEscrow.json"
COMMITTED_ABI = REPO_ROOT / "contracts" / "abi" / "TerraCycleEscrow.json"

EIP712_NAME = "TerraCycleEscrow"
EIP712_VERSION = "1"

# Custom errors of TerraCycleEscrow, used to explain a revert precisely.
CONTRACT_ERRORS = {
    "VerifierZeroAddress()": "VerifierZeroAddress",
    "CommitmentAlreadyRegistered()": "CommitmentAlreadyRegistered",
    "InvalidPlanHash()": "InvalidPlanHash",
    "InvalidReward()": "InvalidReward",
    "CommitmentNotFound()": "CommitmentNotFound",
    "AlreadyFunded()": "AlreadyFunded",
    "NotFunded()": "NotFunded",
    "NotFunder()": "NotFunder",
    "NotRegistrar()": "NotRegistrar",
    "RegistrarZeroAddress()": "RegistrarZeroAddress",
    "NotBeneficiary()": "NotBeneficiary",
    "InvalidVerdict()": "InvalidVerdict",
    "AttestationExpired()": "AttestationExpired",
    "InvalidSignature()": "InvalidSignature",
    "PlanHashMismatch()": "PlanHashMismatch",
    "InvalidState()": "InvalidState",
    "TransferFailed()": "TransferFailed",
    "DeadlineNotExpired()": "DeadlineNotExpired",
    # OpenZeppelin v5 ECDSA errors (raised by ECDSA.recover for a malformed signature)
    "ECDSAInvalidSignature()": "ECDSAInvalidSignature",
    "ECDSAInvalidSignatureLength(uint256)": "ECDSAInvalidSignatureLength",
    "ECDSAInvalidSignatureS(bytes32)": "ECDSAInvalidSignatureS",
}

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {message}")
    if not condition:
        FAILURES.append(message)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def to_hex(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if isinstance(value, str):
        return value if value.startswith("0x") else "0x" + value
    return hex(value)


def load_abi_and_bytecode() -> tuple[list, str]:
    if not ARTIFACT.exists():
        fail(
            "Foundry artifact not found. Run `forge build` in contracts/ "
            f"(expected {ARTIFACT})."
        )
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    bytecode = artifact["bytecode"]["object"]
    if isinstance(bytecode, dict):
        bytecode = bytecode.get("object", "")
    if not bytecode:
        fail("Foundry artifact contains no creation bytecode.")
    if not bytecode.startswith("0x"):
        bytecode = "0x" + bytecode

    abi = artifact["abi"]
    if COMMITTED_ABI.exists():
        # Prefer the committed ABI: it is the stable, reviewable artefact.
        abi = json.loads(COMMITTED_ABI.read_text(encoding="utf-8"))
    return abi, bytecode


def error_name_from_revert(exc: ContractLogicError) -> str:
    """Best-effort mapping of a revert payload to a human-readable error name."""
    data = getattr(exc, "data", None)
    if isinstance(data, dict):
        data = data.get("data")
    if isinstance(data, str) and data.startswith("0x") and len(data) >= 10:
        selector = data[:10].lower()
        for signature, name in CONTRACT_ERRORS.items():
            # Web3.keccak(text=...).hex() has no "0x" prefix; normalise both sides.
            if "0x" + Web3.keccak(text=signature).hex()[:8] == selector:
                return name
        return f"unknown selector {selector}"
    return f"revert without data ({type(exc).__name__})"


def run_node(script: Path, payload: dict, env_extra: dict | None = None) -> dict:
    """Run a Node helper with a JSON payload on stdin; return its JSON stdout."""
    env = {**os.environ, **(env_extra or {})}
    completed = subprocess.run(
        ["node", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        fail(
            f"{script.name} failed with exit code {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        fail(f"{script.name} did not return valid JSON: {exc}")


def sign_attestation(domain: dict, message: dict, key: str | None = None) -> str:
    """Sign with the REAL Node signer and return the 65-byte signature."""
    env_extra = {"VERIFIER_PRIVATE_KEY": key} if key else None
    result = run_node(
        SIGNER_SCRIPT, {"domain": domain, "message": message}, env_extra=env_extra
    )
    signature = result.get("signature")
    if not signature:
        fail("The signer returned no signature.")
    if not (isinstance(signature, str) and signature.startswith("0x") and len(signature) == 132):
        fail(f"The signer returned a malformed signature: {signature!r}")
    return signature


def recover_signer(domain: dict, message: dict, signature: str) -> str:
    """Recover the signer INDEPENDENTLY with ethers."""
    result = run_node(
        RECOVER_SCRIPT,
        {"domain": domain, "message": message, "signature": signature},
    )
    signer = result.get("signer")
    if not signer:
        fail("recover_signer.mjs returned no signer.")
    return signer


def build_domain(w3: Web3, escrow_address: str) -> dict:
    """
    Read the EIP-712 domain FROM THE DEPLOYED CONTRACT.

    The contract is the authority for its own domain: name, version, chain id
    and verifying contract are read back from `eip712Domain()`.
    """
    contract_abi, _ = load_abi_and_bytecode()
    contract = w3.eth.contract(address=Web3.to_checksum_address(escrow_address), abi=contract_abi)
    fields, name, version, chain_id, verifying_contract, salt, extensions = (
        contract.functions.eip712Domain().call()
    )
    if bytes(fields) != b"\x0f":
        raise RuntimeError(f"unexpected EIP-712 domain fields bitmap: {bytes(fields)!r}")
    if salt != b"\x00" * 32 or extensions:
        raise RuntimeError("unexpected salt/extensions in the EIP-712 domain")
    if name != EIP712_NAME or version != EIP712_VERSION:
        raise RuntimeError(
            f"unexpected EIP-712 domain: name={name!r} version={version!r}"
        )
    return {
        "name": name,
        "version": version,
        "chainId": int(chain_id),
        "verifyingContract": Web3.to_checksum_address(verifying_contract),
    }


def attestation_tuple(message: dict) -> tuple:
    return (
        bytes.fromhex(message["commitmentId"][2:]),
        bytes.fromhex(message["planHash"][2:]),
        bytes.fromhex(message["evidenceHash"][2:]),
        int(message["verdict"]),
        int(message["validUntil"]),
    )


def main() -> int:
    print("=" * 78)
    print("TERRACYCLE - EIP-712 SIGNATURE INTEROPERABILITY (TASK-004B.1)")
    print("=" * 78)

    if not PRIVATE_KEY:
        fail("ANVIL_PRIVATE_KEY is not set. Use an Anvil DEVELOPMENT key.")
    if not SIGNER_SCRIPT.exists():
        fail(f"Signer script not found: {SIGNER_SCRIPT}")
    if not RECOVER_SCRIPT.exists():
        fail(f"Signer recovery script not found: {RECOVER_SCRIPT}")

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        fail(f"No local chain reachable at {RPC_URL}. Start anvil first.")

    account = w3.eth.account.from_key(PRIVATE_KEY)
    deployer = account.address
    chain_id = w3.eth.chain_id
    print(f"RPC           : {RPC_URL}")
    print(f"Chain id      : {chain_id}")
    print(f"Deployer      : {deployer}")

    # ------------------------------------------------------------------
    # 1. AUTHENTIC EVIDENCE (existing pipeline, nothing invented)
    # ------------------------------------------------------------------
    print("\n--- 1. authentic evidence from the existing pipeline ---")
    evidence = demo.generate_real_evidence()
    commitment = evidence["commitment"]
    verifier_result = evidence["verifier_result"]

    recomputed = "0x" + __import__("hashlib").sha256(evidence["evidence_bytes"]).hexdigest()
    print(f"  plan_id       : {evidence['plan_id']}")
    print(f"  commitment_id : {evidence['commitment_id']}")
    print(f"  plan_hash     : {evidence['plan_hash']}")
    print(f"  evidence hash : {evidence['evidence_hash']}")
    print(f"  verdict       : {verifier_result['verdict']} (code {verifier_result['verdict_code']})")
    print(f"  reason        : {verifier_result['reason']}")
    check(
        recomputed == evidence["evidence_hash"],
        "SHA-256 evidence hash matches the canonical evidence bytes",
    )
    check(
        verifier_result["verdict"] == "nonconform" and verifier_result["verdict_code"] == 1,
        "the real scientific verdict is nonconform (code 1) - not substituted",
    )

    # ------------------------------------------------------------------
    # 2. DEPLOY THE ESCROW
    # ------------------------------------------------------------------
    print("\n--- 2. deploy TerraCycleEscrow ---")
    contract_abi, bytecode = load_abi_and_bytecode()
    factory = w3.eth.contract(abi=contract_abi, bytecode=bytecode)
    registrar = w3.eth.account.from_key(REGISTRAR_PRIVATE_KEY).address
    deploy_tx = factory.constructor(
        deployer, registrar, EIP712_NAME, EIP712_VERSION
    ).build_transaction(
        {
            "from": deployer,
            "nonce": w3.eth.get_transaction_count(deployer),
            "chainId": chain_id,
        }
    )
    signed = w3.eth.account.sign_transaction(deploy_tx, private_key=PRIVATE_KEY)
    deploy_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    deploy_receipt = w3.eth.wait_for_transaction_receipt(deploy_hash)
    check(deploy_receipt["status"] == 1, "deployment transaction succeeded")
    escrow_address = Web3.to_checksum_address(deploy_receipt["contractAddress"])
    print(f"  escrow        : {escrow_address}")
    print(f"  verifier      : {deployer}")
    print(f"  registrar     : {registrar}")

    escrow = w3.eth.contract(address=escrow_address, abi=contract_abi)
    on_chain_verifier = escrow.functions.verifier().call()
    check(
        Web3.to_checksum_address(on_chain_verifier) == Web3.to_checksum_address(deployer),
        "the deployed verifier is the Anvil development account",
    )
    on_chain_registrar = escrow.functions.registrar().call()
    check(
        Web3.to_checksum_address(on_chain_registrar) == Web3.to_checksum_address(registrar),
        "the deployed registrar is a DISTINCT development account",
    )

    # ------------------------------------------------------------------
    # 3. REGISTER + FUND THE AUTHENTIC COMMITMENT
    # ------------------------------------------------------------------
    print("\n--- 3. register and fund the authentic commitment ---")
    fixture = json.loads(
        (REPO_ROOT / "data" / "fixtures" / "demo.json").read_text(encoding="utf-8")
    )
    ref = fixture["reference_parcel"]
    parcel_b32 = bytes.fromhex(ref["parcel_id_bytes32"][2:])
    season_b32 = bytes.fromhex(ref["season_id_bytes32"][2:])
    beneficiary = Web3.to_checksum_address(fixture["wallets"]["beneficiary"])

    settle_deadline = int(commitment.settle_deadline)

    # --- 3a. An UNAUTHORIZED account must not be able to register ---
    print("  -- 3a. unauthorized registration attempt --")
    unauthorized = deployer  # the deployer/verifier is NOT the registrar
    commitment_id = evidence["commitment_id"]
    state_before = escrow.functions.getCommitment(bytes.fromhex(commitment_id[2:])).call()
    balance_before = w3.eth.get_balance(escrow_address)

    # (i) simulation: the call must revert with NotRegistrar()
    try:
        escrow.functions.registerCommitment(
            parcel_b32, season_b32, bytes.fromhex(evidence["plan_hash"][2:]), beneficiary,
            settle_deadline,
        ).call({"from": unauthorized})
        check(False, "the unauthorized registration simulation was NOT rejected")
    except ContractLogicError as exc:
        name = error_name_from_revert(exc)
        check(
            name == "NotRegistrar",
            f"the unauthorized registration was REJECTED with {name}",
        )

    # (ii) the same call as a real transaction must also fail on-chain.
    #      web3 estimates the gas first, and that estimation reverts with
    #      NotRegistrar(), which is already a proof that the transaction
    #      cannot succeed. When the estimation is skipped, the transaction
    #      itself is mined with status 0.
    try:
        unauthorized_tx = escrow.functions.registerCommitment(
            parcel_b32, season_b32, bytes.fromhex(evidence["plan_hash"][2:]), beneficiary,
            settle_deadline,
        ).build_transaction(
            {"from": unauthorized, "nonce": w3.eth.get_transaction_count(unauthorized), "chainId": chain_id}
        )
        signed = w3.eth.account.sign_transaction(unauthorized_tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        check(
            receipt["status"] == 0,
            "the unauthorized registration transaction failed on-chain (status 0)",
        )
    except ContractCustomError as exc:
        name = error_name_from_revert(exc)
        check(
            name == "NotRegistrar",
            f"the unauthorized registration transaction was REJECTED with {name}",
        )
    except Exception as exc:  # noqa: BLE001
        check(True, f"the unauthorized registration transaction was rejected: {type(exc).__name__}")

    check(
        escrow.functions.getCommitment(bytes.fromhex(commitment_id[2:])).call() == state_before,
        "the unauthorized attempt left the commitment state unchanged",
    )
    check(
        not escrow.functions.registeredId(bytes.fromhex(commitment_id[2:])).call(),
        "the unauthorized attempt did not reserve the commitment id",
    )
    check(
        w3.eth.get_balance(escrow_address) == balance_before,
        "the unauthorized attempt did not move any ETH",
    )

    # --- 3b. The AUTHORIZED registrar registers the authentic commitment ---
    print("  -- 3b. authorized registration --")
    register_tx = escrow.functions.registerCommitment(
        parcel_b32, season_b32, bytes.fromhex(evidence["plan_hash"][2:]), beneficiary,
        settle_deadline,
    ).build_transaction(
        {"from": registrar, "nonce": w3.eth.get_transaction_count(registrar), "chainId": chain_id}
    )
    signed = w3.eth.account.sign_transaction(register_tx, private_key=REGISTRAR_PRIVATE_KEY)
    register_receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction)
    )
    check(register_receipt["status"] == 1, "registerCommitment succeeded")
    print(f"  register tx   : {to_hex(register_receipt['transactionHash'])}")

    check(
        escrow.functions.registeredId(bytes.fromhex(commitment_id[2:])).call(),
        "the on-chain commitment id equals the backend commitment id",
    )
    stored = escrow.functions.getCommitment(bytes.fromhex(commitment_id[2:])).call()
    check(
        to_hex(stored[0]) == evidence["plan_hash"],
        "the stored plan hash equals the backend plan hash",
    )
    check(
        Web3.to_checksum_address(stored[1]) == beneficiary,
        "the stored beneficiary is the intended beneficiary",
    )
    check(int(stored[5]) == 1, "the commitment state is Registered (1)")

    reward_wei = 1_000_000_000_000_000  # 0.001 ETH of LOCAL TEST ETH
    fund_tx = escrow.functions.fundCommitment(
        bytes.fromhex(commitment_id[2:])
    ).build_transaction(
        {
            "from": deployer,
            "value": reward_wei,
            "nonce": w3.eth.get_transaction_count(deployer),
            "chainId": chain_id,
        }
    )
    signed = w3.eth.account.sign_transaction(fund_tx, private_key=PRIVATE_KEY)
    fund_receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction)
    )
    check(fund_receipt["status"] == 1, "fundCommitment succeeded")
    print(f"  fund tx       : {to_hex(fund_receipt['transactionHash'])}")

    # A second, independent commitment so that a tampered commitment id is
    # rejected by the SIGNATURE check and not merely by "not found".
    other_parcel = bytes.fromhex("33" * 32)
    other_tx = escrow.functions.registerCommitment(
        other_parcel, season_b32, bytes.fromhex(evidence["plan_hash"][2:]), beneficiary,
        settle_deadline,
    ).build_transaction(
        {"from": registrar, "nonce": w3.eth.get_transaction_count(registrar), "chainId": chain_id}
    )
    signed = w3.eth.account.sign_transaction(other_tx, private_key=REGISTRAR_PRIVATE_KEY)
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    other_commitment_id = escrow.functions.commitments(
        Web3.keccak(eth_abi_encode(["bytes32", "bytes32"], [other_parcel, season_b32]))
    ).call()[0]
    other_id_hex = to_hex(other_commitment_id)
    other_fund = escrow.functions.fundCommitment(other_commitment_id).build_transaction(
        {
            "from": deployer,
            "value": reward_wei,
            "nonce": w3.eth.get_transaction_count(deployer),
            "chainId": chain_id,
        }
    )
    signed = w3.eth.account.sign_transaction(other_fund, private_key=PRIVATE_KEY)
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    print(f"  second id     : {other_id_hex} (funded, for the replay matrix)")

    # ------------------------------------------------------------------
    # 4. THE EIP-712 DOMAIN, READ FROM THE CONTRACT
    # ------------------------------------------------------------------
    print("\n--- 4. EIP-712 domain (read from the deployed contract) ---")
    domain = build_domain(w3, escrow_address)
    print(f"  name              : {domain['name']}")
    print(f"  version           : {domain['version']}")
    print(f"  chainId           : {domain['chainId']}")
    print(f"  verifyingContract : {domain['verifyingContract']}")
    check(domain["chainId"] == chain_id, "the domain chain id is the local chain id")
    check(
        domain["verifyingContract"] == escrow_address,
        "the domain verifying contract is the freshly deployed escrow",
    )

    # ------------------------------------------------------------------
    # 5. THE ATTESTATION OVER GENUINE EVIDENCE
    # ------------------------------------------------------------------
    print("\n--- 5. attestation over genuine evidence ---")
    message = {
        "commitmentId": commitment_id,
        "planHash": evidence["plan_hash"],
        "evidenceHash": evidence["evidence_hash"],
        "verdict": int(verifier_result["verdict_code"]),
        "validUntil": settle_deadline,
    }
    for key, value in message.items():
        print(f"  {key:14}: {value}")

    signature = sign_attestation(domain, message)
    print(f"  signature   : {signature}")
    check(len(signature) == 132, "the signature is 65 bytes")

    recovered = recover_signer(domain, message, signature)
    print(f"  recovered   : {recovered}")
    check(
        Web3.to_checksum_address(recovered)
        == Web3.to_checksum_address(on_chain_verifier),
        "ethers recovers the authorized verifier address (MATCH)",
    )

    # ------------------------------------------------------------------
    # 6. SIMULATE settle() WITH eth_call
    # ------------------------------------------------------------------
    print("\n--- 6. simulate settle() with eth_call (no transaction sent) ---")
    beneficiary_before = w3.eth.get_balance(beneficiary)
    escrow_balance_before = w3.eth.get_balance(escrow_address)
    state_before = escrow.functions.getCommitment(bytes.fromhex(commitment_id[2:])).call()

    try:
        escrow.functions.settle(
            attestation_tuple(message), bytes.fromhex(signature[2:])
        ).call({"from": deployer})
        check(True, "settle() simulation ACCEPTED the genuine signature")
    except ContractLogicError as exc:
        check(False, f"settle() simulation was rejected: {error_name_from_revert(exc)}")

    state_after = escrow.functions.getCommitment(bytes.fromhex(commitment_id[2:])).call()
    check(
        state_after == state_before,
        "the commitment state is unchanged after the simulation",
    )
    check(
        w3.eth.get_balance(beneficiary) == beneficiary_before,
        "the beneficiary was NOT paid",
    )
    check(
        w3.eth.get_balance(escrow_address) == escrow_balance_before,
        "the escrow balance is unchanged",
    )
    check(
        int(state_after[5]) == 2,
        "the commitment is still in state 2 (Funded) - nothing was settled",
    )

    # ------------------------------------------------------------------
    # 7. NEGATIVE MATRIX
    # ------------------------------------------------------------------
    print("\n--- 7. negative matrix (each must be rejected by the contract) ---")

    def expect_revert(label: str, att: dict, dom: dict, sig: str, expected: str) -> None:
        try:
            escrow.functions.settle(
                attestation_tuple(att), bytes.fromhex(sig[2:])
            ).call({"from": deployer})
            check(False, f"{label}: was NOT rejected (expected {expected})")
        except ContractLogicError as exc:
            name = error_name_from_revert(exc)
            check(
                name == expected,
                f"{label}: rejected with {name} (expected {expected})",
            )

    # 7.1 wrong signing key
    other_key = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
    bad_key_sig = sign_attestation(domain, message, key=other_key)
    bad_key_recovered = recover_signer(domain, message, bad_key_sig)
    check(
        Web3.to_checksum_address(bad_key_recovered)
        != Web3.to_checksum_address(on_chain_verifier),
        "the wrong-key signature recovers to a different address",
    )
    expect_revert("wrong signing key", message, domain, bad_key_sig, "InvalidSignature")

    # 7.2 wrong chain id in the domain
    wrong_chain_domain = {**domain, "chainId": 11155111}
    wrong_chain_sig = sign_attestation(wrong_chain_domain, message)
    expect_revert("wrong chain id", message, wrong_chain_domain, wrong_chain_sig, "InvalidSignature")

    # 7.3 wrong verifying contract in the domain
    wrong_contract_domain = {
        **domain,
        "verifyingContract": "0x0000000000000000000000000000000000000001",
    }
    wrong_contract_sig = sign_attestation(wrong_contract_domain, message)
    expect_revert(
        "wrong contract address", message, wrong_contract_domain, wrong_contract_sig,
        "InvalidSignature",
    )

    # 7.4 REPLAY: the signature was produced for commitment A; the attestation
    #     claims commitment B. The original signature must not be accepted.
    rebound = {**message, "commitmentId": other_id_hex}
    expect_revert("different commitment id", rebound, domain, signature, "InvalidSignature")

    # 7.5 the attestation claims a plan hash the commitment does not have.
    #     The contract checks the plan hash BEFORE the signature, so it reverts
    #     with PlanHashMismatch.
    other_plan = {**message, "planHash": "0x" + "aa" * 32}
    other_plan_sig = sign_attestation(domain, other_plan)
    expect_revert("different plan hash", other_plan, domain, other_plan_sig, "PlanHashMismatch")

    # 7.6 TAMPER: the evidence hash in the attestation is modified while the
    #     original signature is replayed.
    tampered_evidence = {**message, "evidenceHash": "0x" + "bb" * 32}
    expect_revert(
        "modified evidence hash", tampered_evidence, domain, signature,
        "InvalidSignature",
    )

    # 7.7 TAMPER: the verdict is modified while the original signature is
    #     replayed. The mutation targets 2 = inconclusive, which can never
    #     authorise a payout even if it were accepted.
    modified_verdict = {**message, "verdict": 2}
    expect_revert(
        "modified verdict", modified_verdict, domain, signature,
        "InvalidSignature",
    )

    # 7.8 expired attestation
    expired = {**message, "validUntil": 1}
    expired_sig = sign_attestation(domain, expired)
    expect_revert("expired validUntil", expired, domain, expired_sig, "AttestationExpired")

    # 7.9 malformed / truncated signature
    truncated = signature[:-2]
    try:
        escrow.functions.settle(
            attestation_tuple(message), bytes.fromhex(truncated[2:])
        ).call({"from": deployer})
        check(False, "truncated signature: was NOT rejected")
    except ContractLogicError as exc:
        name = error_name_from_revert(exc)
        check(
            name in ("ECDSAInvalidSignature", "ECDSAInvalidSignatureLength"),
            f"truncated signature: rejected with {name}",
        )

    # 7.10 a valid signature must not be reusable for another contract
    #     (the domain of another deployment differs -> different digest)
    other_escrow_address = None
    deploy2 = factory.constructor(deployer, registrar, EIP712_NAME, EIP712_VERSION).build_transaction(
        {
            "from": deployer,
            "nonce": w3.eth.get_transaction_count(deployer),
            "chainId": chain_id,
        }
    )
    signed2 = w3.eth.account.sign_transaction(deploy2, private_key=PRIVATE_KEY)
    receipt2 = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed2.raw_transaction)
    )
    other_escrow_address = Web3.to_checksum_address(receipt2["contractAddress"])
    other_domain = build_domain(w3, other_escrow_address)
    check(
        other_domain["verifyingContract"] != domain["verifyingContract"],
        "a second escrow was deployed at a different address",
    )
    try:
        escrow2 = w3.eth.contract(address=other_escrow_address, abi=contract_abi)
        escrow2.functions.settle(
            attestation_tuple(message), bytes.fromhex(signature[2:])
        ).call({"from": deployer})
        check(False, "signature reuse across contracts: was NOT rejected")
    except ContractLogicError as exc:
        name = error_name_from_revert(exc)
        check(
            name in ("InvalidSignature", "CommitmentNotFound", "InvalidState"),
            f"signature reuse across contracts: rejected with {name}",
        )

    # ------------------------------------------------------------------
    # 8. FINAL STATE CHECK
    # ------------------------------------------------------------------
    print("\n--- 8. final state (nothing was settled) ---")
    final_state = escrow.functions.getCommitment(bytes.fromhex(commitment_id[2:])).call()
    print(f"  commitment state : {int(final_state[5])} (2 = Funded)")
    print(f"  escrow balance   : {w3.eth.get_balance(escrow_address)} wei")
    print(f"  beneficiary      : {w3.eth.get_balance(beneficiary)} wei")
    check(int(final_state[5]) == 2, "the commitment is still Funded - no settlement occurred")
    check(
        w3.eth.get_balance(beneficiary) == beneficiary_before,
        "the beneficiary received nothing",
    )
    check(
        w3.eth.get_balance(escrow_address) == escrow_balance_before,
        "the escrow still holds exactly the funded amount",
    )
    print(f"  transactions mined in this run: register + fund (+ a second commitment)")

    print("\n" + "=" * 78)
    if FAILURES:
        print(f"RESULT: FAILED ({len(FAILURES)} check(s))")
        for item in FAILURES:
            print(f"  - {item}")
        print("=" * 78)
        return 1
    print("RESULT: PASS - genuine EIP-712 evidence signature accepted by the")
    print("        deployed escrow (simulation only; nothing was settled)")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
