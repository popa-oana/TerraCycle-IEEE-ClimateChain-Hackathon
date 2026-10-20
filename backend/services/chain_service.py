import json
from pathlib import Path
from typing import Any

from web3 import Web3
from web3.types import TxReceipt

from backend.config import get_settings

ABI_FALLBACK_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "out"
    / "TerraCycleEscrow.sol"
    / "TerraCycleEscrow.json"
)

METHOD_SIGNATURES = {
    "register_commitment": "registerCommitment",
    "fund_commitment": "fundCommitment",
    "settle": "settle",
    "refund": "refund",
}


class ChainVerificationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def load_contract_abi() -> list[dict[str, Any]]:
    settings = get_settings()

    abi_path = getattr(settings, "contract_abi_path", "") or ""
    candidates = [Path(abi_path)] if abi_path else []
    candidates.append(ABI_FALLBACK_PATH)

    for candidate in candidates:
        if candidate and candidate.exists():
            artifact = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(artifact, dict) and "abi" in artifact:
                return artifact["abi"]
            if isinstance(artifact, list):
                return artifact

    raise ChainVerificationError(
        "CONTRACT_ABI_UNAVAILABLE",
        "Contract ABI is not available. Compile the contract or set CONTRACT_ABI_PATH.",
    )


def create_web3(rpc_url: str | None = None) -> Web3:
    settings = get_settings()
    url = rpc_url or getattr(settings, "chain_rpc_url", "") or ""
    if not url:
        raise ChainVerificationError("CHAIN_RPC_UNAVAILABLE", "CHAIN_RPC_URL is not configured.")
    return Web3(Web3.HTTPProvider(url))


def verify_transaction(
    w3: Web3,
    *,
    tx_hash: str,
    tx_type: str,
    contract_address: str,
    expected_chain_id: int,
    commitment_id: str | None = None,
    parcel_id: str | None = None,
    season_id: str | None = None,
    plan_hash: str | None = None,
    amount_wei: int | None = None,
    funder: str | None = None,
    beneficiary: str | None = None,
) -> dict[str, Any]:
    if tx_type not in METHOD_SIGNATURES:
        raise ChainVerificationError("INVALID_TX_TYPE", f"Unknown tx_type '{tx_type}'.")

    abi = load_contract_abi()
    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)

    checks: list[str] = []

    chain_id = w3.eth.chain_id
    if chain_id != expected_chain_id:
        raise ChainVerificationError(
            "WRONG_NETWORK",
            f"Transaction chain id {chain_id} does not match expected {expected_chain_id}.",
        )
    checks.append("network_matches")

    receipt = w3.eth.get_transaction_receipt(tx_hash)
    if receipt is None:
        raise ChainVerificationError("TX_NOT_FOUND", f"Transaction '{tx_hash}' was not found.")

    if receipt.get("status") is None:
        raise ChainVerificationError(
            "PENDING_CONFIRMATION",
            f"Transaction '{tx_hash}' is not yet mined.",
        )
    if receipt.get("status") != 1:
        raise ChainVerificationError("TX_FAILED", f"Transaction '{tx_hash}' failed on-chain.")
    checks.append("receipt_status_success")

    if (receipt.get("to") or "").lower() != contract_address.lower():
        raise ChainVerificationError(
            "TX_MISMATCH",
            f"Transaction was sent to {receipt.get('to')}, expected {contract_address}.",
        )
    checks.append("contract_matches")

    tx = w3.eth.get_transaction(tx_hash)
    decoded = _decode_contract_call(contract, tx)
    if decoded is None:
        raise ChainVerificationError("TX_MISMATCH", "Transaction calldata could not be decoded against the contract ABI.")

    function_name, params = decoded
    expected_function = METHOD_SIGNATURES[tx_type]
    if function_name != expected_function:
        raise ChainVerificationError(
            "TX_MISMATCH",
            f"Transaction called '{function_name}', expected '{expected_function}'.",
        )
    checks.append(f"method_matches_{expected_function}")

    if tx_type == "register_commitment":
        _check_register(params, parcel_id, season_id, plan_hash, checks)
    elif tx_type == "fund_commitment":
        _check_fund(params, commitment_id, tx, amount_wei, checks)
    elif tx_type == "settle":
        _check_settle(params, commitment_id, plan_hash, checks)
    elif tx_type == "refund":
        _check_refund(params, commitment_id, checks)

    return {
        "tx_hash": tx_hash,
        "tx_type": tx_type,
        "status": "confirmed",
        "block_number": receipt.get("blockNumber"),
        "checks_passed": checks,
    }


def _decode_contract_call(contract: Any, tx: Any) -> tuple[str, dict[str, Any]] | None:
    try:
        return contract.decode_function_input(tx["input"])
    except Exception:
        return None


def _check_register(
    params: dict[str, Any],
    parcel_id: str | None,
    season_id: str | None,
    plan_hash: str | None,
    checks: list[str],
) -> None:
    if parcel_id is not None:
        if _hex(params.get("parcelId")) != _hex(parcel_id):
            raise ChainVerificationError("TX_MISMATCH", "parcelId does not match the registered commitment.")
        checks.append("parcel_and_season_match")
    if season_id is not None:
        if _hex(params.get("seasonId")) != _hex(season_id):
            raise ChainVerificationError("TX_MISMATCH", "seasonId does not match the registered commitment.")
        checks.append("parcel_and_season_match")
    if plan_hash is not None:
        if _hex(params.get("planHash")) != _hex(plan_hash):
            raise ChainVerificationError("PLAN_HASH_MISMATCH", "planHash does not match the stored commitment.")
        checks.append("plan_hash_matches")


def _check_fund(
    params: dict[str, Any],
    commitment_id: str | None,
    tx: Any,
    amount_wei: int | None,
    checks: list[str],
) -> None:
    if commitment_id is not None:
        if _hex(params.get("commitmentId")) != _hex(commitment_id):
            raise ChainVerificationError("TX_MISMATCH", "commitmentId does not match the expected commitment.")
        checks.append("commitment_id_matches")
    if amount_wei is not None:
        if int(tx.get("value", 0)) != int(amount_wei):
            raise ChainVerificationError("TX_MISMATCH", "Transaction value does not match the expected reward.")
        checks.append("amount_matches")


def _check_settle(
    params: dict[str, Any],
    commitment_id: str | None,
    plan_hash: str | None,
    checks: list[str],
) -> None:
    attestation = params.get("attestation")
    if not isinstance(attestation, (tuple, list, dict)):
        raise ChainVerificationError("TX_MISMATCH", "settle() is missing the attestation struct.")

    att = _normalize_struct(attestation)
    if commitment_id is not None:
        if _hex(att.get("commitmentId")) != _hex(commitment_id):
            raise ChainVerificationError("TX_MISMATCH", "Attestation commitmentId does not match.")
        checks.append("commitment_id_matches")
    if plan_hash is not None:
        if _hex(att.get("planHash")) != _hex(plan_hash):
            raise ChainVerificationError("PLAN_HASH_MISMATCH", "Attestation planHash does not match.")
        checks.append("plan_hash_matches")


def _check_refund(
    params: dict[str, Any],
    commitment_id: str | None,
    checks: list[str],
) -> None:
    if commitment_id is not None:
        if _hex(params.get("commitmentId")) != _hex(commitment_id):
            raise ChainVerificationError("TX_MISMATCH", "commitmentId does not match the expected commitment.")
        checks.append("commitment_id_matches")


def _normalize_struct(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    names = ["commitmentId", "planHash", "evidenceHash", "verdict", "validUntil"]
    return {name: val for name, val in zip(names, value)}


def _hex(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if isinstance(value, int):
        return hex(value)
    return str(value).lower()


def read_contract_state(
    w3: Web3,
    *,
    contract_address: str,
    commitment_id: str,
) -> dict[str, Any]:
    abi = load_contract_abi()
    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)
    result = contract.functions.getCommitment(bytes.fromhex(commitment_id[2:])).call()
    plan_hash, beneficiary, funder, reward, deadline, state = result
    return {
        "plan_hash": _hex(plan_hash),
        "beneficiary": beneficiary,
        "funder": funder,
        "reward_wei": int(reward),
        "settle_deadline": int(deadline),
        "state": int(state),
    }