"""The stream aggregator's consume loop.

Reads `fraudguard.transactions.v1`, Avro-decodes each message against the
Schema Registry, and folds it into the Redis feature store. See ADR-0008
for the offset-commit strategy, schema caching, and poison-message handling
this module implements.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Protocol

from aiokafka import AIOKafkaConsumer, ConsumerRecord

from fraudguard_common.logging import get_logger
from fraudguard_common.metrics import (
    observe_aggregator_processing_duration,
    record_aggregator_message,
)
from fraudguard_events import TRANSACTIONS_V1, decode, schema_id_of
from fraudguard_events.schema_registry import SchemaRegistryClient

logger = get_logger(__name__)

#: Chosen so a second instance could later join the same group and split
#: partitions -- see ADR-0008. Not exercised (single instance) yet.
CONSUMER_GROUP_ID = "fraudguard-aggregator"


class FeatureStoreWriter(Protocol):
    """What the aggregator needs from a feature store.

    Structural rather than `fraudguard_features.FeatureStore` by name, so
    tests can substitute a fake that never opens a real Redis connection --
    the real round trip is covered by this service's integration tests.
    """

    async def record_transaction(
        self,
        account_id: str,
        event_id: str,
        merchant_id: str,
        occurred_at: datetime,
    ) -> None: ...


class SchemaCache:
    """Resolves a wire-format schema ID to its Avro schema, once per ID.

    Without this, decoding would cost one Schema Registry round trip per
    message instead of per distinct schema version.
    """

    def __init__(self, registry: SchemaRegistryClient) -> None:
        self._registry = registry
        self._schemas: dict[int, dict[str, Any]] = {}

    async def get(self, schema_id: int) -> dict[str, Any]:
        cached = self._schemas.get(schema_id)
        if cached is not None:
            return cached
        schema_json = await self._registry.get_schema(schema_id)
        schema: dict[str, Any] = json.loads(schema_json)
        self._schemas[schema_id] = schema
        return schema


async def apply_transaction_event(
    store: FeatureStoreWriter, record: dict[str, Any]
) -> None:
    """Fold one decoded `TransactionReceived` record into the feature store."""
    await store.record_transaction(
        account_id=str(record["account_id"]),
        event_id=str(record["event_id"]),
        merchant_id=record["merchant_id"],
        occurred_at=record["occurred_at"],
    )


class Aggregator:
    """Owns the Kafka consumer, the Schema Registry client, and the Redis
    writes for one consumer-group member.

    `store` is accepted as a dependency (not constructed internally) so
    tests can inject a fake without a real Redis connection, the same
    pattern `gateway.app.create_app` uses for `database` and `events`.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        schema_registry_url: str,
        store: FeatureStoreWriter,
        *,
        group_id: str = CONSUMER_GROUP_ID,
    ) -> None:
        # AIOKafkaConsumer itself -- not just .start() -- needs a running
        # event loop to construct (it calls asyncio.get_event_loop()
        # internally), the same trap EventProducer's AIOKafkaProducer hit
        # (ADR-0006). Constructing it eagerly here would make Aggregator(...)
        # unsafe to call from asgi.py's module-level `create_app()`, which
        # runs before uvicorn's event loop exists. Deferred to start().
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._registry = SchemaRegistryClient(schema_registry_url)
        self._schema_cache = SchemaCache(self._registry)
        self._store = store
        self.running = False

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            TRANSACTIONS_V1.name,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        self.running = True

    async def stop(self) -> None:
        self.running = False
        if self._consumer is not None:
            await self._consumer.stop()
        await self._registry.close()

    async def run_forever(self) -> None:
        """Consume until cancelled. Intended to run as a background task."""
        if self._consumer is None:
            raise RuntimeError("Aggregator.start() must be called before run_forever()")
        try:
            async for message in self._consumer:
                await self._process(message)
        finally:
            self.running = False

    async def _process(self, message: ConsumerRecord) -> None:
        started_at = time.monotonic()
        try:
            schema_id = schema_id_of(message.value)
            schema = await self._schema_cache.get(schema_id)
            record = decode(schema, message.value)
            await apply_transaction_event(self._store, record)
            record_aggregator_message(outcome="applied")
        except Exception:
            # Logged and skipped, not retried -- see ADR-0008. A poison
            # message must not block every later message on this partition.
            logger.exception(
                "failed to process transaction event; skipping",
                extra={
                    "kafka_topic": message.topic,
                    "kafka_partition": message.partition,
                    "kafka_offset": message.offset,
                },
            )
            record_aggregator_message(outcome="skipped")
        finally:
            observe_aggregator_processing_duration(time.monotonic() - started_at)
            # _process() is only ever invoked from run_forever()'s loop,
            # which already guards self._consumer being set; this narrows
            # the type for mypy rather than re-raising for a state that
            # cannot occur in practice.
            if self._consumer is not None:
                await self._consumer.commit()
