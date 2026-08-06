"""Integration tests against a real Postgres instance.

Requires the docker compose stack (`docker compose up -d postgres`), which
is why every test here is marked `integration` -- see the marker
registered in the root `pyproject.toml`. Table creation/teardown is scoped
to this module's own fixture rather than depending on Alembic migrations
existing yet, and always tears down so a later Alembic-managed schema does
not collide with a table this suite left behind.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from fraudguard_db.models import (
    Base,
    Decision,
    DecisionOutcome,
    Label,
    LabelSource,
    Transaction,
)
from fraudguard_db.session import Database, DatabaseSettings

pytestmark = pytest.mark.integration


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database(DatabaseSettings())
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield database
    finally:
        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await database.dispose()


async def test_ping_succeeds_against_a_reachable_postgres(db: Database) -> None:
    await db.ping()  # raises on failure; nothing to assert on success


async def test_transaction_decision_and_label_round_trip(db: Database) -> None:
    transaction = Transaction(
        account_id=uuid4(),
        merchant_id="merchant-1",
        amount=Decimal("42.50"),
        currency="USD",
        occurred_at=datetime.now(UTC),
    )

    async with db.session() as session:
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

        session.add(
            Decision(
                transaction_id=transaction.id,
                outcome=DecisionOutcome.APPROVE,
                risk_score=0.12,
                model_version=None,
            )
        )
        session.add(
            Label(
                transaction_id=transaction.id,
                is_fraud=False,
                source=LabelSource.MANUAL_REVIEW,
            )
        )
        await session.commit()

    async with db.session() as session:
        stored = await session.scalar(
            select(Transaction).where(Transaction.id == transaction.id)
        )
        assert stored is not None
        assert stored.merchant_id == "merchant-1"
        assert stored.amount == Decimal("42.50")

        decision = await session.scalar(
            select(Decision).where(Decision.transaction_id == transaction.id)
        )
        assert decision is not None
        assert decision.outcome == DecisionOutcome.APPROVE

        label = await session.scalar(
            select(Label).where(Label.transaction_id == transaction.id)
        )
        assert label is not None
        assert label.is_fraud is False


async def test_decision_transaction_id_is_unique(db: Database) -> None:
    transaction = Transaction(
        account_id=uuid4(),
        merchant_id="merchant-1",
        amount=Decimal("10.00"),
        currency="USD",
        occurred_at=datetime.now(UTC),
    )

    async with db.session() as session:
        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

        session.add(
            Decision(
                transaction_id=transaction.id,
                outcome=DecisionOutcome.APPROVE,
                risk_score=0.1,
            )
        )
        await session.commit()

        session.add(
            Decision(
                transaction_id=transaction.id,
                outcome=DecisionOutcome.DECLINE,
                risk_score=0.9,
            )
        )
        with pytest.raises(Exception, match=r"unique|duplicate"):
            await session.commit()
