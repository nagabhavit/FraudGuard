"""Integration test for POST /v1/transactions against the real stack.

Requires the docker compose stack (postgres, kafka, schema-registry) --
marked `integration` for the same reason as fraudguard-db's and
fraudguard-events' own integration suites. Verifies the full chain for
real: HTTP 202, a genuine Postgres row, and a genuine Avro-encoded Kafka
message that decodes back to the same transaction.
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

from fraudguard_db.models import Transaction
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
        assert response.status_code == 202
        transaction_id = UUID(response.json()["transaction_id"])

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
