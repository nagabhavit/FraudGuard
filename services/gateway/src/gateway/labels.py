"""Ground-truth labels for transactions, arriving after the fact.

The gateway owns this write path for the same reason it owns the read side
of `GET /v1/transactions` (ADR-0012): it already has the `fraudguard-db`
session, and recording a label is a cheap, indexed Postgres insert with no
feature-service or model-service call in it, so it does not compete with
the hot path for either dependency. See ADR-0014.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from fraudguard_common.errors import NotFoundError
from fraudguard_common.metrics import record_gateway_label
from fraudguard_db.models import Label, LabelSource, Transaction

router = APIRouter(tags=["labels"])


class LabelCreate(BaseModel):
    is_fraud: bool
    source: LabelSource
    notes: Annotated[str | None, Field(default=None)] = None


class LabelSummary(BaseModel):
    """A label as embedded in `GET /v1/transactions` (ADR-0014).

    Omits `transaction_id` -- it is redundant once nested under the
    transaction it belongs to, the same reason `DecisionSummary` omits it.
    """

    id: UUID
    is_fraud: bool
    source: LabelSource
    notes: str | None
    labeled_at: datetime


class LabelRead(LabelSummary):
    transaction_id: UUID


@router.post(
    "/v1/transactions/{transaction_id}/labels",
    status_code=status.HTTP_201_CREATED,
    response_model=LabelRead,
)
async def create_label(
    transaction_id: UUID, payload: LabelCreate, request: Request
) -> LabelRead:
    async with request.app.state.db.session() as session:
        exists = await session.scalar(
            select(Transaction.id).where(Transaction.id == transaction_id)
        )
        if exists is None:
            raise NotFoundError(f"transaction {transaction_id} does not exist")

        label = Label(
            transaction_id=transaction_id,
            is_fraud=payload.is_fraud,
            source=payload.source,
            notes=payload.notes,
        )
        session.add(label)
        await session.commit()
        await session.refresh(label)

    record_gateway_label(source=payload.source.value, is_fraud=payload.is_fraud)

    return LabelRead(
        id=label.id,
        transaction_id=label.transaction_id,
        is_fraud=label.is_fraud,
        source=label.source,
        notes=label.notes,
        labeled_at=label.labeled_at,
    )
