import json
import pytest
from backend.hashing import canonical_bytes, hash_snapshot, compute_commitment_id


def test_hashing_key_order_independence():
    """Chei în ordine diferită produc aceiași octeți canonici și același SHA-256."""
    payload_a = {
        "parcel_id": "parcel_01",
        "season_id": "season-2024",
        "policy": {"type": "cover", "version": 1, "active": True},
    }
    payload_b = {
        "policy": {"version": 1, "active": True, "type": "cover"},
        "season_id": "season-2024",
        "parcel_id": "parcel_01",
    }
    bytes_a, hash_a = hash_snapshot(payload_a)
    bytes_b, hash_b = hash_snapshot(payload_b)

    assert bytes_a == bytes_b
    assert hash_a == hash_b
    assert hash_a.startswith("0x")
    assert len(hash_a) == 66


def test_hashing_unicode_support():
    """Diacriticele și caracterele Unicode sunt păstrate stabil în UTF-8 fără escape ascii."""
    payload = {"region": "Dolj, Craiova — Câmp demonstrativ", "cultură": "grâu"}
    raw_bytes, digest = hash_snapshot(payload)
    assert "Câmp demonstrativ".encode("utf-8") in raw_bytes
    assert "\\u" not in raw_bytes.decode("utf-8")


def test_hashing_mutation_detection():
    """O singură modificare de valoare produce un hash complet diferit."""
    base = {
        "parcel_id": "parcel_01",
        "history": [{"year": 2022, "crop": "wheat"}],
    }
    mutated = {
        "parcel_id": "parcel_01",
        "history": [{"year": 2022, "crop": "maize"}],
    }
    _, hash_base = hash_snapshot(base)
    _, hash_mut = hash_snapshot(mutated)
    assert hash_base != hash_mut


def test_hashing_rejects_floats():
    """Float-urile sunt strict interzise în snapshot-uri canonice."""
    with pytest.raises(TypeError, match="Floats are forbidden"):
        canonical_bytes({"threshold": 0.35})

    with pytest.raises(TypeError, match="Floats are forbidden"):
        canonical_bytes({"nested": {"scores": [1, 2, 3.14]}})


def test_compute_commitment_id():
    """Verifică că calculul commitment_id produce keccak256 identic cu Solidity."""
    p_bytes32 = "0x1111111111111111111111111111111111111111111111111111111111111111"
    s_bytes32 = "0x2222222222222222222222222222222222222222222222222222222222222222"

    cid = compute_commitment_id(p_bytes32, s_bytes32)
    assert cid == "0x3e92e0db88d6afea9edc4eedf62fffa4d92bcdfc310dccbe943747fe8302e871"
