from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base

HASH_RE = "^0x[0-9a-f]{64}$"
ADDR_RE = "^0x[0-9a-fA-F]{40}$"


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Parcel(Base):
    __tablename__ = "parcels"

    parcel_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    geometry_path: Mapped[str] = mapped_column(String(255))  # data/parcels/*.geojson
    area_ha: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


class Plan(Base):
    __tablename__ = "plans"

    plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.parcel_id"))
    season_id: Mapped[str] = mapped_column(String(16))
    crop_history: Mapped[list] = mapped_column(JSONB)
    treatments: Mapped[list] = mapped_column(JSONB, server_default="[]")
    requested_crop_id: Mapped[str | None] = mapped_column(String(64))
    rotations: Mapped[list] = mapped_column(JSONB)  # generated variants
    climate_source: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = _now()


class Commitment(Base):
    __tablename__ = "commitments"

    commitment_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.plan_id"), unique=True)
    parcel_id: Mapped[str] = mapped_column(ForeignKey("parcels.parcel_id"))
    season_id: Mapped[str] = mapped_column(String(16))
    rotation_id: Mapped[str] = mapped_column(String(64))
    verification_policy_id: Mapped[str] = mapped_column(String(64))
    beneficiary_address: Mapped[str] = mapped_column(String(42))
    funder_address: Mapped[str | None] = mapped_column(String(42))
    reward_wei: Mapped[Decimal | None] = mapped_column(Numeric(78, 0))
    plan_hash: Mapped[str] = mapped_column(String(66))
    plan_snapshot: Mapped[bytes] = mapped_column(LargeBinary)  # exact canonical bytes
    settle_deadline: Mapped[int] = mapped_column(BigInteger)  # unix seconds
    state: Mapped[str] = mapped_column(String(16), server_default="prepared")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("parcel_id", "season_id", name="uq_commitments_parcel_season"),
        CheckConstraint(
            "state IN ('prepared','registered','funded','paid','negative','refunded')",
            name="ck_commitments_state",
        ),
        CheckConstraint(f"commitment_id ~ '{HASH_RE}'", name="ck_commitments_id_format"),
        CheckConstraint(f"plan_hash ~ '{HASH_RE}'", name="ck_commitments_hash_format"),
        CheckConstraint(
            f"beneficiary_address ~ '{ADDR_RE}'", name="ck_commitments_beneficiary_format"
        ),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    tx_hash: Mapped[str] = mapped_column(String(66), primary_key=True)
    commitment_id: Mapped[str] = mapped_column(ForeignKey("commitments.commitment_id"))
    tx_type: Mapped[str] = mapped_column(String(32))  # validated in the API layer
    actor: Mapped[str] = mapped_column(String(16))  # validated in the API layer
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    checks_passed: Mapped[list] = mapped_column(JSONB, server_default="[]")
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        CheckConstraint(f"tx_hash ~ '{HASH_RE}'", name="ck_transactions_hash_format"),
        CheckConstraint(
            "status IN ('pending','confirmed','failed')", name="ck_transactions_status"
        ),
    )


class Verdict(Base):
    __tablename__ = "verdicts"

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    commitment_id: Mapped[str] = mapped_column(ForeignKey("commitments.commitment_id"))
    evidence_hash: Mapped[str] = mapped_column(String(66))
    evidence_snapshot: Mapped[bytes] = mapped_column(LargeBinary)  # exact bytes hashed
    verdict: Mapped[str] = mapped_column(String(16))
    verdict_code: Mapped[int] = mapped_column(SmallInteger)
    reason_codes: Mapped[list] = mapped_column(JSONB, server_default="[]")
    attestation: Mapped[dict | None] = mapped_column(JSONB)
    signature: Mapped[str | None] = mapped_column(String(132))
    valid_until: Mapped[int | None] = mapped_column(BigInteger)
    model_version: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        CheckConstraint(
            "(verdict = 'conform' AND verdict_code = 0) OR "
            "(verdict = 'nonconform' AND verdict_code = 1) OR "
            "(verdict = 'inconclusive' AND verdict_code = 2)",
            name="ck_verdicts_single_mapping",
        ),
        CheckConstraint(f"evidence_hash ~ '{HASH_RE}'", name="ck_verdicts_hash_format"),
    )
