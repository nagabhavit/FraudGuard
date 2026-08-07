"""Transaction ingestion.

Accepts a transaction, persists it durably (Postgres is the system of
record, ADR-0005), and publishes it to the cold path (ADR-0006). No
decisioning yet -- that arrives with the feature store and model service
(Milestones 7-9). This milestone's job is getting the event durably onto
Kafka, not scoring it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field, field_validator

from fraudguard_common.logging import get_logger
from fraudguard_db.models import Transaction
from fraudguard_events import TRANSACTIONS_V1

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


class TransactionAccepted(BaseModel):
    transaction_id: UUID
    status: str = "accepted"


@router.post(
    "/v1/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TransactionAccepted,
)
async def create_transaction(
    payload: TransactionCreate, request: Request
) -> TransactionAccepted:
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

    await _publish_transaction_received(request, transaction)

    return TransactionAccepted(transaction_id=transaction.id)


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
