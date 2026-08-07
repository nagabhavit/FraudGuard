"""Integration test for the real consume loop: a real Kafka message, Avro-
decoded against a real Schema Registry, folded into a real Redis feature
store.

Requires the docker compose stack (kafka, schema-registry, redis) -- marked
`integration` for the same reason as the other services' integration
suites. Uses a fresh, unique consumer-group id per test run so it is
unaffected by any offsets a previous run or manual testing left behind;
`auto_offset_reset="earliest"` (Aggregator's fixed setting) means a new
group replays the whole topic, which is why this test waits for its own
distinctive account_id to appear rather than asserting on message counts.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from aggregator.consumer import Aggregator
from fraudguard_events import TRANSACTIONS_V1, EventProducer
from fraudguard_features import FeatureStore

pytestmark = pytest.mark.integration

_KAFKA_BOOTSTRAP_SERVERS = "localhost:29092"
_SCHEMA_REGISTRY_URL = "http://localhost:8081"


async def _wait_for_velocity(
    store: FeatureStore, account_id: str, timeout_seconds: float = 15.0
) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        velocity = await store.get_velocity(account_id, "1m")
        if velocity > 0:
            return velocity
        await asyncio.sleep(0.25)
    return 0


async def test_consumer_applies_a_real_kafka_message_to_redis() -> None:
    account_id = uuid4()
    event_id = str(uuid4())
    now = datetime.now(UTC)

    producer = EventProducer(_KAFKA_BOOTSTRAP_SERVERS, _SCHEMA_REGISTRY_URL)
    store = FeatureStore()
    aggregator = Aggregator(
        _KAFKA_BOOTSTRAP_SERVERS,
        _SCHEMA_REGISTRY_URL,
        store,
        group_id=f"test-aggregator-{uuid4()}",
    )

    consume_task: asyncio.Task[None] | None = None
    try:
        await producer.start()
        await producer.register_schema(TRANSACTIONS_V1, "transaction_received")

        await aggregator.start()
        consume_task = asyncio.create_task(aggregator.run_forever())

        await producer.publish(
            TRANSACTIONS_V1,
            key=str(account_id).encode(),
            record={
                "event_id": event_id,
                "transaction_id": str(uuid4()),
                "account_id": str(account_id),
                "merchant_id": "merchant-a",
                "amount": Decimal("10.00"),
                "currency": "USD",
                "occurred_at": now,
                "received_at": now,
            },
        )

        velocity = await _wait_for_velocity(store, str(account_id))
        assert velocity == 1

        vector = await store.get_feature_vector(str(account_id))
        assert vector["distinct_merchants_24h"] == 1
    finally:
        if consume_task is not None:
            consume_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consume_task
        await aggregator.stop()
        await producer.stop()
        await store.close()
