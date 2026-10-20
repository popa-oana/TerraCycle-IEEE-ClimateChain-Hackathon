"""
Demo script showing TX_MISMATCH and related error handling.

Run with: python -m scripts.demo_tx_mismatch
"""
import sys
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from unittest.mock import MagicMock, patch

from backend.services.chain_service import ChainVerificationError, verify_transaction


MINIMAL_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "parcelId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "seasonId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "planHash", "type": "bytes32"},
            {"internalType": "address", "name": "beneficiary", "type": "address"},
            {"internalType": "uint64", "name": "settleDeadline", "type": "uint64"},
        ],
        "name": "registerCommitment",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "commitmentId", "type": "bytes32"}],
        "name": "fundCommitment",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"components": [
                {"internalType": "bytes32", "name": "commitmentId", "type": "bytes32"},
                {"internalType": "bytes32", "name": "planHash", "type": "bytes32"},
                {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
                {"internalType": "uint8", "name": "verdict", "type": "uint8"},
                {"internalType": "uint64", "name": "validUntil", "type": "uint64"},
            ], "internalType": "struct VerificationResult", "name": "attestation", "type": "tuple"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "settle",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "commitmentId", "type": "bytes32"}],
        "name": "refund",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "commitmentId", "type": "bytes32"}],
        "name": "getCommitment",
        "outputs": [
            {"internalType": "bytes32", "name": "planHash", "type": "bytes32"},
            {"internalType": "address", "name": "beneficiary", "type": "address"},
            {"internalType": "address", "name": "funder", "type": "address"},
            {"internalType": "uint256", "name": "reward", "type": "uint256"},
            {"internalType": "uint64", "name": "settleDeadline", "type": "uint64"},
            {"internalType": "uint8", "name": "state", "type": "uint8"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


def make_mock_w3():
    w3 = MagicMock()
    w3.eth.chain_id = 31337
    w3.to_checksum_address = lambda x: x
    return w3


def make_mock_receipt(status=1, to="0x1234567890123456789012345678901234567890", block_number=12345):
    r = MagicMock()
    r.get = lambda k, default=None: {
        "status": status,
        "to": to,
        "blockNumber": block_number,
    }.get(k, default)
    r.status = status
    r.to = to
    r.blockNumber = block_number
    return r


def make_mock_tx(input_data="0x1234", value=0):
    t = MagicMock()
    t.input = input_data
    t.value = value
    return t


def test_tx_mismatch_wrong_contract():
    """Transaction sent to wrong contract address."""
    w3 = make_mock_w3()
    w3.eth.get_transaction_receipt.return_value = make_mock_receipt(to="0x9999999999999999999999999999999999999999")
    w3.eth.get_transaction.return_value = make_mock_tx()
    w3.eth.contract.return_value.decode_function_input.return_value = ("registerCommitment", {"parcelId": "0x1111", "seasonId": "0x2222", "planHash": "0x3333"})

    with patch("backend.services.chain_service.load_contract_abi", return_value=MINIMAL_ABI):
        try:
            from backend.services.chain_service import verify_transaction
            verify_transaction(
                w3=w3,
                tx_hash="0xabc",
                tx_type="register_commitment",
                contract_address="0x1234567890123456789012345678901234567890",
                expected_chain_id=31337,
                plan_hash="0x3333",
                parcel_id="0x1111",
                season_id="0x2222",
            )
        except Exception as e:
            return "[OK] Wrong contract: " + str(e)
    return "FAILED: no exception"


def test_tx_mismatch_wrong_plan_hash():
    """Register with mismatched planHash."""
    w3 = make_mock_w3()
    w3.eth.get_transaction_receipt.return_value = make_mock_receipt()
    w3.eth.get_transaction.return_value = make_mock_tx()
    w3.eth.contract.return_value.decode_function_input.return_value = ("registerCommitment", {"parcelId": "0x1111", "seasonId": "0x2222", "planHash": "0x9999"})

    with patch("backend.services.chain_service.load_contract_abi", return_value=MINIMAL_ABI):
        try:
            from backend.services.chain_service import verify_transaction
            verify_transaction(
                w3=w3,
                tx_hash="0xabc",
                tx_type="register_commitment",
                contract_address="0x1234567890123456789012345678901234567890",
                expected_chain_id=31337,
                plan_hash="0x3333",
                parcel_id="0x1111",
                season_id="0x2222",
            )
        except Exception as e:
            return "[OK] Wrong plan hash: " + str(e)
    return "FAILED: no exception"


def test_tx_mismatch_wrong_method():
    """Transaction called wrong contract method."""
    w3 = make_mock_w3()
    w3.eth.get_transaction_receipt.return_value = make_mock_receipt()
    w3.eth.get_transaction.return_value = make_mock_tx()
    w3.eth.contract.return_value.decode_function_input.return_value = ("fundCommitment", {})

    with patch("backend.services.chain_service.load_contract_abi", return_value=MINIMAL_ABI):
        try:
            from backend.services.chain_service import verify_transaction
            verify_transaction(
                w3=w3,
                tx_hash="0xabc",
                tx_type="register_commitment",
                contract_address="0x1234567890123456789012345678901234567890",
                expected_chain_id=31337,
                plan_hash="0x3333",
                parcel_id="0x1111",
                season_id="0x2222",
            )
        except Exception as e:
            return "[OK] Wrong method: " + str(e)
    return "FAILED: no exception"


def test_wrong_network():
    """Transaction on wrong chain."""
    w3 = make_mock_w3()
    w3.eth.chain_id = 1  # Mainnet instead of 31337
    w3.eth.get_transaction_receipt.return_value = make_mock_receipt()

    with patch("backend.services.chain_service.load_contract_abi", return_value=MINIMAL_ABI):
        try:
            from backend.services.chain_service import verify_transaction
            verify_transaction(
                w3=w3,
                tx_hash="0xabc",
                tx_type="register_commitment",
                contract_address="0x1234567890123456789012345678901234567890",
                expected_chain_id=31337,
            )
        except Exception as e:
            return "[OK] Wrong network: " + str(e)
    return "FAILED: no exception"


def test_pending_confirmation():
    """Transaction not yet mined."""
    w3 = make_mock_w3()
    r = MagicMock()
    r.get = lambda k, d=None: None if k == "status" else d
    r.status = None
    w3.eth.get_transaction_receipt.return_value = r

    with patch("backend.services.chain_service.load_contract_abi", return_value=MINIMAL_ABI):
        try:
            from backend.services.chain_service import verify_transaction
            verify_transaction(
                w3=w3,
                tx_hash="0xabc",
                tx_type="register_commitment",
                contract_address="0x1234567890123456789012345678901234567890",
                expected_chain_id=31337,
            )
        except Exception as e:
            return "[OK] Pending: " + str(e)
    return "FAILED: no exception"


def test_tx_failed():
    """Transaction reverted on-chain."""
    w3 = make_mock_w3()
    w3.eth.get_transaction_receipt.return_value = make_mock_receipt(status=0)

    with patch("backend.services.chain_service.load_contract_abi", return_value=MINIMAL_ABI):
        try:
            from backend.services.chain_service import verify_transaction
            verify_transaction(
                w3=w3,
                tx_hash="0xabc",
                tx_type="register_commitment",
                contract_address="0x1234567890123456789012345678901234567890",
                expected_chain_id=31337,
            )
        except Exception as e:
            return "[OK] Failed tx: " + str(e)
    return "FAILED: no exception"


def test_tx_not_found():
    """Transaction doesn't exist."""
    w3 = make_mock_w3()
    w3.eth.get_transaction_receipt.return_value = None

    with patch("backend.services.chain_service.load_contract_abi", return_value=MINIMAL_ABI):
        try:
            from backend.services.chain_service import verify_transaction
            verify_transaction(
                w3=w3,
                tx_hash="0xabc",
                tx_type="register_commitment",
                contract_address="0x1234567890123456789012345678901234567890",
                expected_chain_id=31337,
            )
        except Exception as e:
            return "[OK] Not found: " + str(e)
    return "FAILED: no exception"


if __name__ == "__main__":
    tests = [
        test_tx_mismatch_wrong_contract,
        test_tx_mismatch_wrong_plan_hash,
        test_tx_mismatch_wrong_method,
        test_wrong_network,
        test_pending_confirmation,
        test_tx_failed,
        test_tx_not_found,
    ]

    passed = 0
    for test in tests:
        try:
            result = test()
            if result.startswith("[OK]"):
                passed += 1
                print(result)
            else:
                print("FAILED: " + test.__name__)
        except Exception as e:
            print("FAILED " + test.__name__ + ": " + str(e))

    print(f"\n{passed}/{len(tests)} error scenarios demonstrated")