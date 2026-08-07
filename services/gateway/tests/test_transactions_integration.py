"""Integration test for POST /v1/transactions against the real stack.

Requires the docker compose stack (postgres, kafka, schema-registry,
feature-service, model-service) -- marked `integration` for the same reason
as fraudguard-db's and fraudguard-events' own integration suites. Verifies
the full chain for real: HTTP 200 with a genuine model decision, a genuine
Postgres `Decision` row, and a genuine Avro-encoded Kafka message that
decodes back to the same transaction. The degradation-ladder fallback
(ADR-0009) is exercised separately, against a fake `ScoringDependency` that
raises `UpstreamUnavailableError`, in
`test_create_transaction_falls_back_when_scoring_is_unreachable` below --
still against the real Postgres, just not real feature/model-service network
calls: a real unreachable host (e.g. a closed port) does not fail
predictably fast on every platform, and this test only needs to prove the
fallback path persists correctly, not that httpx's own timeout works.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer, ConsumerRecord
from fastapi.testclient import TestClient
from sqlalchemy import select

from fraudguard_common.errors import UpstreamUnavailableError
from fraudguard_db.models import Decision, DecisionOutcome, Transaction
from fraudguard_db.session import Database, DatabaseSettings
from fraudguard_events import TRANSACTIONS_V1, decode
from fraudguard_events.schema_registry import SchemaRegistryClient
from gateway.app import create_app
from gateway.settings import GatewaySettings

pytestmark = pytest.mark.integration


async def _next_message(consumer: AIOKafkaConsumer) -> ConsumerRecord:
    async with asyncio.timeout(10.0):
        return await consumer.getone()


async def test_create_transaction_persists_and_publishes_for_real() -> None:
    app = create_app(GatewaySettings(_env_file=None))
    account_id = uuid4()
    payload = {
        "account_id": str(account_id),
        "merchant_id": "integration-test-merchant",
        "amount": "17.25",
        "currency": "GBP",
        "occurred_at": "2026-08-07T09:00:00Z",
    }

    consumer = AIOKafkaConsumer(
        TRANSACTIONS_V1.name,
        bootstrap_servers="localhost:29092",
        auto_offset_reset="latest",
    )
    await consumer.start()
    try:
        # Subscription must be live before the POST, or the message this
        # test cares about arrives before this consumer starts listening.
        await consumer.seek_to_end()

        with TestClient(app) as client:
            response = client.post("/v1/transactions", json=payload)
        assert response.status_code == 200
        body = response.json()
        transaction_id = UUID(body["transaction_id"])
        # The real model scored this: model_version is populated, not the
        # fallback rule's None (ADR-0009).
        assert body["model_version"] is not None
        assert body["model_version"].startswith("fraud-lgbm-")
        assert body["outcome"] in {"approve", "decline", "review"}
        assert 0.0 <= body["risk_score"] <= 1.0

        db = Database(DatabaseSettings())
        try:
            async with db.session() as session:
                stored = await session.scalar(
                    select(Transaction).where(Transaction.id == transaction_id)
                )
                assert stored is not None
                assert stored.account_id == account_id
                assert stored.amount == Decimal("17.25")
                assert stored.currency == "GBP"

                decision = await session.scalar(
                    select(Decision).where(Decision.transaction_id == transaction_id)
                )
            assert decision is not None
            assert decision.outcome.value == body["outcome"]
            assert decision.model_version == body["model_version"]
            assert decision.latency_ms is not None
        finally:
            await db.dispose()

        message = await _next_message(consumer)
        registry = SchemaRegistryClient("http://localhost:8081")
        try:
            schema_id = int.from_bytes(message.value[1:5], "big")
            schema = json.loads(await registry.get_schema(schema_id))
            record = decode(schema, message.value)
        finally:
            await registry.close()

        assert record["transaction_id"] == transaction_id
        assert record["account_id"] == account_id
        assert record["amount"] == Decimal("17.25")
        assert message.key == str(account_id).encode()
    finally:
        await consumer.stop()


class _UnavailableScoringClient:
    async def get_features(self, account_id: UUID) -> dict[str, int]:
        raise UpstreamUnavailableError("feature-service unreachable")

    async def score(self, **kwargs: object) -> dict[str, object]:
        raise AssertionError("must not be called: get_features already failed")

    async def aclose(self) -> None:
        pass


async def test_create_transaction_falls_back_when_scoring_is_unreachable() -> None:
    """The degradation ladder (ADR-0009), against a real Postgres.

    Injects a fake `ScoringDependency` that always raises
    `UpstreamUnavailableError` -- the real infrastructure this suite needs
    is Postgres, not feature-service/model-service, which is the whole
    point of this test: it proves a fallback decision persists correctly
    against a real database, not that HTTP against an unreachable host
    times out (that is `HttpScoringClient`'s own hermetic tests,
    `test_gateway_scoring.py`, against a mocked transport).
    """
    app = create_app(
        GatewaySettings(_env_file=None), scoring=_UnavailableScoringClient()
    )
    account_id = uuid4()
    payload = {
        "account_id": str(account_id),
        "merchant_id": "integration-test-merchant",
        "amount": "999.00",
        "currency": "USD",
        "occurred_at": "2026-08-07T09:00:00Z",
    }

    with TestClient(app) as client:
        response = client.post("/v1/transactions", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] is None
    assert body["outcome"] == DecisionOutcome.REVIEW.value
    transaction_id = UUID(body["transaction_id"])

    db = Database(DatabaseSettings())
    try:
        async with db.session() as session:
            decision = await session.scalar(
                select(Decision).where(Decision.transaction_id == transaction_id)
            )
        assert decision is not None
        assert decision.model_version is None
        assert decision.reason_codes is None
    finally:
        await db.dispose()
