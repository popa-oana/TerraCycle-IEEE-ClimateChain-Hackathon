import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db import get_db
from backend.models import Commitment, Transaction
from backend.services.chain_service import ChainVerificationError, create_web3, verify_transaction

router = APIRouter(tags=["transactions"])


def _load_settings() -> dict:
    s = get_settings()
    return {
        "chain_rpc_url": s.chain_rpc_url,
        "chain_id": s.chain_id,
        "contract_address": s.contract_address,
    }


@router.post("/commitments/{commitment_id}/transactions")
def record_transaction(commitment_id: str, tx_hash: str, tx_type: str, db: Session = Depends(get_db)):
    commitment = db.get(Commitment, commitment_id)
    if not commitment:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "COMMITMENT_NOT_FOUND", "message": f"Commitment '{commitment_id}' does not exist."}},
        )

    if commitment.state != "funded":
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "INVALID_STATE", "message": f"Commitment must be funded to verify, current state: {commitment.state}."}},
        )

    existing = db.get(Transaction, tx_hash)
    if existing:
        return {
            "commitment_id": existing.commitment_id,
            "tx_hash": existing.tx_hash,
            "tx_type": existing.tx_type,
            "status": existing.status,
            "block_number": existing.block_number,
            "checks_passed": existing.checks_passed,
        }

    settings = _load_settings()
    w3 = create_web3(settings["chain_rpc_url"])

    try:
        result = verify_transaction(
            w3=w3,
            tx_hash=tx_hash,
            tx_type=tx_type,
            contract_address=settings["contract_address"],
            expected_chain_id=settings["chain_id"],
            commitment_id=commitment.commitment_id,
            parcel_id=_hex(commitment.parcel_id) if commitment.parcel_id else None,
            season_id=_hex(commitment.season_id) if commitment.season_id else None,
            plan_hash=commitment.plan_hash,
        )
    except ChainVerificationError as exc:
        raise HTTPException(
            status_code=409 if exc.code in ("TX_MISMATCH", "PLAN_HASH_MISMATCH", "WRONG_NETWORK") else 502,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "CHAIN_SERVICE_ERROR", "message": f"Chain verification failed: {exc}"}},
        )

    tx = Transaction(
        tx_hash=tx_hash,
        commitment_id=commitment_id,
        tx_type=tx_type,
        actor=_infer_actor(tx_type),
        status="confirmed",
        block_number=result.get("block_number"),
        checks_passed=result.get("checks_passed", []),
    )
    db.add(tx)

    _update_commitment_state(db, commitment, result.get("tx_type"))
    db.commit()
    db.refresh(tx)

    return {
        "commitment_id": tx.commitment_id,
        "tx_hash": tx.tx_hash,
        "tx_type": tx.tx_type,
        "status": tx.status,
        "block_number": tx.block_number,
        "checks_passed": tx.checks_passed,
    }


def _infer_actor(tx_type: str) -> str:
    mapping = {
        "register_commitment": "farmer",
        "fund_commitment": "funder",
        "settle": "verifier",
        "refund": "funder",
    }
    return mapping.get(tx_type, "unknown")


def _update_commitment_state(db: Session, commitment: Commitment, tx_type: str) -> None:
    transitions = {
        "register_commitment": "registered",
        "fund_commitment": "funded",
        "settle": "paid",
        "refund": "refunded",
    }
    new_state = transitions.get(tx_type)
    if new_state:
        commitment.state = new_state


def _hex(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("0x"):
        return value.lower()
    return "0x" + value.lower()
