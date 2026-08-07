"""Async Kafka producer wrapper.

Wraps `aiokafka.AIOKafkaProducer` with Avro encoding against the Schema
Registry. One instance per process; a service creates it at startup and
disposes it on shutdown -- the same lifecycle shape as
`fraudguard_db.session.Database`, so the gateway's app factory composes the
two the same way.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from aiokafka import AIOKafkaProducer

from fraudguard_events.schema_registry import SchemaRegistryClient
from fraudguard_events.serialization import encode
from fraudguard_events.topics import TopicSpec


def load_schema(name: str) -> dict[str, Any]:
    """Load a bundled Avro schema by filename stem (e.g. "transaction_received").

    Reads via `importlib.resources` rather than a path relative to
    `__file__`, so this works identically whether fraudguard-events is
    installed editable (local dev) or as a built wheel (a service image).
    """
    schema_text = (
        resources.files("fraudguard_events.schemas")
        .joinpath(f"{name}.avsc")
        .read_text("utf-8")
    )
    schema: dict[str, Any] = json.loads(schema_text)
    return schema


class EventProducer:
    """Publishes Avro-encoded events, registering each topic's schema once
    (via `register_schema`) rather than on every `publish` call.
    """

    def __init__(self, bootstrap_servers: str, schema_registry_url: str) -> None:
        # AIOKafkaProducer itself -- not just .start() -- needs a running
        # event loop to construct (it calls asyncio.get_event_loop()
        # internally), unlike SQLAlchemy's async engine. Constructing it
        # eagerly here would make EventProducer(...) unsafe to call from
        # synchronous code (e.g. a plain, non-async test or app factory),
        # so it is deferred to start(), which is only ever awaited from
        # inside a running loop.
        self._bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None
        self._registry = SchemaRegistryClient(schema_registry_url)
        self._registered: dict[str, tuple[int, dict[str, Any]]] = {}

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
        await self._producer.start()

    async def register_schema(self, topic: TopicSpec, schema_name: str) -> None:
        schema = load_schema(schema_name)
        subject = f"{topic.name}-value"
        schema_id = await self._registry.register(subject, json.dumps(schema))
        self._registered[topic.name] = (schema_id, schema)

    async def publish(
        self, topic: TopicSpec, key: bytes, record: dict[str, Any]
    ) -> None:
        if self._producer is None:
            raise RuntimeError("EventProducer.start() must be called before publish()")
        registered = self._registered.get(topic.name)
        if registered is None:
            raise RuntimeError(
                f"no schema registered for topic {topic.name!r}; "
                "call register_schema() first"
            )
        schema_id, schema = registered
        payload = encode(schema, schema_id, record)
        await self._producer.send_and_wait(topic.name, value=payload, key=key)

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
        await self._registry.close()
