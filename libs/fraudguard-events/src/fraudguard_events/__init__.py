"""Shared Kafka topics, Avro schemas, and event publishing for FraudGuard
services.

Every producer and consumer imports topic declarations and schemas from
here rather than each keeping its own copy. See ADR-0006.
"""

from fraudguard_events.producer import EventProducer, load_schema
from fraudguard_events.schema_registry import SchemaRegistryClient, SchemaRegistryError
from fraudguard_events.serialization import decode, encode, schema_id_of
from fraudguard_events.settings import EventSettings, LocalEventSettings
from fraudguard_events.topics import ALL_TOPICS, TRANSACTIONS_V1, TopicSpec

__version__ = "0.1.0"

__all__ = [
    "ALL_TOPICS",
    "TRANSACTIONS_V1",
    "EventProducer",
    "EventSettings",
    "LocalEventSettings",
    "SchemaRegistryClient",
    "SchemaRegistryError",
    "TopicSpec",
    "decode",
    "encode",
    "load_schema",
    "schema_id_of",
]
