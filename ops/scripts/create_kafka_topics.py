"""Explicitly create FraudGuard's Kafka topics.

`KAFKA_AUTO_CREATE_TOPICS_ENABLE` is `false` (docker-compose.yml) precisely
so a topic's partition count and retention are a reviewed decision in
`fraudguard_events.topics`, not whatever the first producer happened to
send. Run this once against a fresh stack, or any time `ALL_TOPICS` changes:

    uv run --all-packages python ops/scripts/create_kafka_topics.py

Idempotent: an already-existing topic is left untouched and reported, not
recreated or errored on -- safe to run again after adding a new topic.
"""

from __future__ import annotations

import asyncio
import contextlib
import os

from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from fraudguard_events.topics import ALL_TOPICS, TopicSpec

# The external listener (docker-compose.yml) -- this script runs on the
# host, the same way `alembic` and `uv run uvicorn` do, not inside the
# compose network.
_DEFAULT_BOOTSTRAP_SERVERS = "localhost:29092"


def _new_topic(spec: TopicSpec) -> NewTopic:
    return NewTopic(
        name=spec.name,
        num_partitions=spec.partitions,
        replication_factor=spec.replication_factor,
        topic_configs={"retention.ms": str(spec.retention_ms)},
    )


async def create_topics(bootstrap_servers: str) -> None:
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        missing = [spec for spec in ALL_TOPICS if spec.name not in existing]

        for spec in ALL_TOPICS:
            if spec.name in existing:
                print(f"exists   {spec.name} (left unchanged)")

        if not missing:
            return

        # Lost a race with another run between list_topics() and here -- the
        # topic exists either way, which is the only thing this script
        # promises.
        with contextlib.suppress(TopicAlreadyExistsError):
            await admin.create_topics([_new_topic(spec) for spec in missing])

        for spec in missing:
            print(f"created  {spec.name} (partitions={spec.partitions})")
    finally:
        await admin.close()


def main() -> None:
    bootstrap_servers = os.environ.get(
        "KAFKA_BOOTSTRAP_SERVERS", _DEFAULT_BOOTSTRAP_SERVERS
    )
    asyncio.run(create_topics(bootstrap_servers))


if __name__ == "__main__":
    main()
