import hashlib
import json
from typing import Any
from eth_abi import encode
from web3 import Web3


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """
    Serializes a payload to canonical UTF-8 bytes:
    - Rejects floats (only ints, strings, bools, null, dicts, lists allowed)
    - Keys are sorted recursively
    - Compact separators (',', ':'), no extraneous whitespace
    - UTF-8 encoding with ensure_ascii=False
    """
    def reject_float(value: Any) -> None:
        if isinstance(value, float):
            raise TypeError("Floats are forbidden in canonical snapshots; use fixed-precision ints or strings.")
        if isinstance(value, dict):
            for child in value.values():
                reject_float(child)
        elif isinstance(value, list):
            for child in value:
                reject_float(child)

    reject_float(payload)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def hash_snapshot(payload: dict[str, Any]) -> tuple[bytes, str]:
    """
    Computes canonical bytes and its SHA-256 hash (prefixed with '0x').
    Returns (raw_canonical_bytes, '0x' + 64 hex chars).
    """
    content = canonical_bytes(payload)
    digest = "0x" + hashlib.sha256(content).hexdigest()
    return content, digest


def compute_commitment_id(parcel_id_bytes32: str, season_id_bytes32: str) -> str:
    """
    Computes EVM commitmentId = keccak256(abi.encode(bytes32, bytes32))
    Both inputs must be 0x-prefixed 64-hex strings.
    Returns 0x + 64 hex chars matching Solidity output.
    """
    p_hex = parcel_id_bytes32[2:] if parcel_id_bytes32.startswith("0x") else parcel_id_bytes32
    s_hex = season_id_bytes32[2:] if season_id_bytes32.startswith("0x") else season_id_bytes32

    p_bytes = bytes.fromhex(p_hex)
    s_bytes = bytes.fromhex(s_hex)

    if len(p_bytes) != 32 or len(s_bytes) != 32:
        raise ValueError("Both parcel_id_bytes32 and season_id_bytes32 must be exactly 32 bytes.")

    encoded = encode(["bytes32", "bytes32"], [p_bytes, s_bytes])
    res = Web3().keccak(encoded).hex()
    return "0x" + res if not res.startswith("0x") else res
