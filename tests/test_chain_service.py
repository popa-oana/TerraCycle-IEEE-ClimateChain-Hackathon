"""Simple import and basic tests for chain_service."""

from backend.services.chain_service import ChainVerificationError, verify_transaction


def test_chain_service_imports():
    """Verify chain_service imports without error."""
    assert ChainVerificationError is not None
    assert verify_transaction is not None


def test_chain_verification_error():
    """Test ChainVerificationError can be raised and caught."""
    try:
        raise ChainVerificationError("TEST_CODE", "test message")
    except ChainVerificationError as e:
        assert e.code == "TEST_CODE"
        assert e.message == "test message"


if __name__ == "__main__":
    test_chain_service_imports()
    test_chain_verification_error()
    print("All basic tests passed")