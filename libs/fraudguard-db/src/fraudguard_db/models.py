"""SQLAlchemy models for the FraudGuard system of record.

One definition of the schema, imported by every service that touches
Postgres (the gateway today; the aggregator and labels service later) and by
the Alembic migrations in `db/migrations/`. Kept in its own package rather
than inline in one service -- see ADR-0005.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, UniqueConstraint, func, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base.

    Alembic's `env.py` autogenerates against `Base.metadata`, so every model
    must inherit from this one class or a migration silently omits it.
    """


class DecisionOutcome(StrEnum):
    APPROVE = "approve"
    DECLINE = "decline"
    REVIEW = "review"


class LabelSource(StrEnum):
    CHARGEBACK = "chargeback"
    MANUAL_REVIEW = "manual_review"
    CUSTOMER_REPORT = "customer_report"


class Transaction(Base):
    """A single authorization request as it arrived at the gateway.

    `raw_payload` keeps the original request body: the model that scored it
    will be retrained long after the typed columns were designed, and the
    untyped payload is what makes that retraining possible without having
    replayed the transaction from upstream.
    """

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    merchant_id: Mapped[str]
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)

    decision: Mapped[Decision | None] = relationship(
        back_populates="transaction", uselist=False
    )
    labels: Mapped[list[Label]] = relationship(back_populates="transaction")


class Decision(Base):
    """The outcome the model (or a fallback rule) produced for one transaction.

    `UniqueConstraint("transaction_id")` encodes one decision per
    transaction. A re-score is a new transaction, not a second decision row
    -- otherwise "the" decision for a transaction becomes ambiguous the
    moment a second row exists.
    """

    __tablename__ = "decisions"
    __table_args__ = (UniqueConstraint("transaction_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transactions.id"))
    outcome: Mapped[DecisionOutcome] = mapped_column(
        SqlEnum(
            DecisionOutcome,
            native_enum=False,
            validate_strings=True,
            # Without this, SQLAlchemy stores the member NAME ("APPROVE"),
            # not its value ("approve") -- inconsistent with how the same
            # enum serializes everywhere else (JSON, logs) and a trap for
            # anything that queries this column with raw SQL.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        )
    )
    risk_score: Mapped[float]
    # Null model_version means a rule-based fallback decided, not the model --
    # the degradation ladder (docs/architecture.md) depends on being able to
    # tell those apart after the fact.
    model_version: Mapped[str | None]
    reason_codes: Mapped[list[str] | None] = mapped_column(JSONB)
    latency_ms: Mapped[float | None]
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    transaction: Mapped[Transaction] = relationship(back_populates="decision")


class Label(Base):
    """Ground truth for a transaction, arriving after the fact.

    Multiple labels per transaction are allowed (a chargeback and a later
    manual review can disagree); reconciling them is a training-pipeline
    concern, not a constraint the schema should enforce.
    """

    __tablename__ = "labels"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transactions.id"), index=True
    )
    is_fraud: Mapped[bool]
    source: Mapped[LabelSource] = mapped_column(
        SqlEnum(
            LabelSource,
            native_enum=False,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        )
    )
    notes: Mapped[str | None] = mapped_column(Text)
    labeled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    transaction: Mapped[Transaction] = relationship(back_populates="labels")
