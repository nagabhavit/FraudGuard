"""Transaction ingestion and hot-path scoring.

Accepts a transaction, persists it durably (Postgres is the system of
record, ADR-0005), scores it inline against feature-service and
model-service (ADR-0009), persists the resulting `Decision`, and publishes
the transaction to the cold path (ADR-0006). Scoring runs after the
transaction is durably committed and before the response, so the response
carries a real decision, not just an acknowledgement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from fraudguard_common.logging import get_logger
from fraudguard_common.metrics import (
    record_gateway_decision,
    record_gateway_kafka_publish,
)
from fraudguard_db.models import Decision, DecisionOutcome, Transaction
from fraudguard_events import TRANSACTIONS_V1
from gateway.scoring import score_transaction

logger = get_logger(__name__)
router = APIRouter(tags=["transactions"])


class TransactionCreate(BaseModel):
    account_id: UUID
    merchant_id: Annotated[str, Field(min_length=1)]
    amount: Annotated[Decimal, Field(gt=0)]
    currency: Annotated[str, Field(min_length=3, max_length=3)]
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        # A naive datetime stored against a TIMESTAMPTZ column is an
        # asyncpg error, not a silent UTC assumption -- and silently
        # assuming UTC for a financial transaction's timestamp is exactly
        # the kind of guess that should be a validation error instead.
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value


class TransactionDecision(BaseModel):
    transaction_id: UUID
    outcome: DecisionOutcome
    risk_score: float
    model_version: str | None
    reason_codes: list[str] | None


class DecisionSummary(BaseModel):
    outcome: DecisionOutcome
    risk_score: float
    model_version: str | None
    reason_codes: list[str] | None
    decided_at: datetime


class TransactionFeedItem(BaseModel):
    """One row of the dashboard's transaction feed (ADR-0012).

    `decision` is nullable: a transaction can exist without one if the
    process crashed between the two writes `create_transaction` makes below.
    """

    transaction_id: UUID
    account_id: UUID
    merchant_id: str
    amount: Decimal
    currency: str
    occurred_at: datetime
    decision: DecisionSummary | None


class TransactionFeedPage(BaseModel):
    items: list[TransactionFeedItem]
    limit: int
    offset: int


@router.post(
    "/v1/transactions",
    status_code=status.HTTP_200_OK,
    response_model=TransactionDecision,
)
async def create_transaction(
    payload: TransactionCreate, request: Request
) -> TransactionDecision:
    transaction = Transaction(
        account_id=payload.account_id,
        merchant_id=payload.merchant_id,
        amount=payload.amount,
        currency=payload.currency.upper(),
        occurred_at=payload.occurred_at,
    )

    async with request.app.state.db.session() as session:
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

    settings = request.app.state.settings
    scored = await score_transaction(
        request.app.state.scoring,
        account_id=transaction.account_id,
        amount=transaction.amount,
        fallback_threshold=settings.fallback_amount_threshold,
        budget_ms=settings.scoring_budget_ms,
    )

    decision = Decision(
        transaction_id=transaction.id,
        outcome=scored.outcome,
        risk_score=scored.risk_score,
        model_version=scored.model_version,
        reason_codes=scored.reason_codes,
        latency_ms=scored.latency_ms,
    )
    async with request.app.state.db.session() as session:
        session.add(decision)
        await session.commit()

    record_gateway_decision(
        outcome=scored.outcome.value, model_version=scored.model_version
    )

    await _publish_transaction_received(request, transaction)

    return TransactionDecision(
        transaction_id=transaction.id,
        outcome=scored.outcome,
        risk_score=scored.risk_score,
        model_version=scored.model_version,
        reason_codes=scored.reason_codes,
    )


@router.get("/v1/transactions", response_model=TransactionFeedPage)
async def list_transactions(
    request: Request,
    limit: Annotated[int, Query(gt=0, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionFeedPage:
    """The dashboard's transaction feed (ADR-0012): most recent first.

    `selectinload` fetches every row's decision in one extra query, not one
    per row -- an N+1 here would turn a 50-row page into 51 round trips.
    """
    async with request.app.state.db.session() as session:
        result = await session.scalars(
            select(Transaction)
            .options(selectinload(Transaction.decision))
            .order_by(Transaction.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        transactions = result.all()

    items = [
        TransactionFeedItem(
            transaction_id=transaction.id,
            account_id=transaction.account_id,
            merchant_id=transaction.merchant_id,
            amount=transaction.amount,
            currency=transaction.currency,
            occurred_at=transaction.occurred_at,
            decision=(
                DecisionSummary(
                    outcome=transaction.decision.outcome,
                    risk_score=transaction.decision.risk_score,
                    model_version=transaction.decision.model_version,
                    reason_codes=transaction.decision.reason_codes,
                    decided_at=transaction.decision.decided_at,
                )
                if transaction.decision is not None
                else None
            ),
        )
        for transaction in transactions
    ]
    return TransactionFeedPage(items=items, limit=limit, offset=offset)


async def _publish_transaction_received(
    request: Request, transaction: Transaction
) -> None:
    """Best-effort: a publish failure does not fail the request.

    The transaction is already durably committed to Postgres by the time
    this runs. Failing the request here would make payment authorization
    depend on Kafka's availability, which ADR-0006 rules out. The gap this
    leaves -- persisted but never published -- is a known, documented
    limitation (ADR-0006), not an oversight.
    """
    record = {
        "event_id": str(uuid4()),
        "transaction_id": str(transaction.id),
        "account_id": str(transaction.account_id),
        "merchant_id": transaction.merchant_id,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "occurred_at": transaction.occurred_at,
        "received_at": datetime.now(UTC),
    }
    try:
        await request.app.state.events.publish(
            TRANSACTIONS_V1,
            key=str(transaction.account_id).encode(),
            record=record,
        )
    except Exception:
        logger.exception(
            "failed to publish transaction event",
            extra={"transaction_id": str(transaction.id)},
        )
        record_gateway_kafka_publish(outcome="failure")
        return
    record_gateway_kafka_publish(outcome="success")
