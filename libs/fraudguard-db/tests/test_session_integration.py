"""Integration tests against a real Postgres instance.

Requires the docker compose stack (`docker compose up -d postgres`), which
is why every test here is marked `integration` -- see the marker
registered in the root `pyproject.toml`.

The fixture ensures the schema exists (`create_all`, which SQLAlchemy skips
per-table if already present) but deliberately never drops it. This same
schema is what `db/migrations/` manages and what a running gateway depends
on -- against a shared local Postgres (as opposed to CI's ephemeral, per-run
container) an earlier version of this fixture dropped the tables in its
teardown unconditionally, silently destroying an Alembic-applied schema the
moment this suite ran. `alembic_version` still claimed "head" afterwards;
the tables underneath it were simply gone. Tests must not have side effects
outside their own sandbox on state they do not own.
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
        # checkfirst=True (the default) makes this a no-op against a
        # database Alembic already migrated -- it does not drop and does
        # not need to, since the schema these models describe and the
        # schema the latest migration creates are the same schema.
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield database
    finally:
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
