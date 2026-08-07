"""Kafka topic declarations for FraudGuard.

The single source of truth for topic name, partition count, replication
factor, and retention. Both `ops/scripts/create_kafka_topics.py` (which
creates them explicitly -- `KAFKA_AUTO_CREATE_TOPICS_ENABLE` is off, see
`docker-compose.yml`) and every producer/consumer import from here, rather
than each hardcoding its own copy that can drift.
"""

from __future__ import annotations

from dataclasses import dataclass

_SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class TopicSpec:
    name: str
    partitions: int
    replication_factor: int
    retention_ms: int


TRANSACTIONS_V1 = TopicSpec(
    name="fraudguard.transactions.v1",
    # Keyed by account_id (see transaction_received.avsc): 3 partitions gives
    # the stream aggregator real parallelism to reason about locally without
    # pretending this dev cluster needs production-scale partitioning.
    partitions=3,
    # Single broker locally; production uses 3 (docker-compose.yml, Milestone 29).
    replication_factor=1,
    # Long enough to replay a bad aggregator deploy; short enough not to
    # matter for a laptop's disk.
    retention_ms=_SEVEN_DAYS_MS,
)

ALL_TOPICS: tuple[TopicSpec, ...] = (TRANSACTIONS_V1,)
