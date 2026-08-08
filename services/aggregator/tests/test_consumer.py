"""Unit tests for SchemaCache and apply_transaction_event -- no Kafka or
Redis required. The full consume loop (Aggregator.run_forever) is covered
by test_consumer_integration.py against the real stack.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from aggregator.consumer import Aggregator, SchemaCache, apply_transaction_event
from fraudguard_common.metrics import render_metrics


def _metric_value(metric_name: str, **labels: str) -> float:
    text = render_metrics()[0].decode()
    label_str = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    prefix = f"{metric_name}{{{label_str}}} " if labels else f"{metric_name} "
    for line in text.splitlines():
        if line.startswith(prefix):
            return float(line.removeprefix(prefix))
    return 0.0


class _FakeRegistry:
    def __init__(self) -> None:
        self.calls = 0

    async def get_schema(self, schema_id: int) -> str:
        self.calls += 1
        return json.dumps(
            {"type": "record", "name": f"Schema{schema_id}", "fields": []}
        )


class _FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, datetime]] = []

    async def record_transaction(
        self, account_id: str, event_id: str, merchant_id: str, occurred_at: datetime
    ) -> None:
        self.calls.append((account_id, event_id, merchant_id, occurred_at))


async def test_schema_cache_fetches_once_and_reuses_for_the_same_id() -> None:
    registry = _FakeRegistry()
    cache = SchemaCache(registry)  # type: ignore[arg-type]

    first = await cache.get(7)
    second = await cache.get(7)

    assert first == second
    assert registry.calls == 1


async def test_schema_cache_fetches_separately_for_different_ids() -> None:
    registry = _FakeRegistry()
    cache = SchemaCache(registry)  # type: ignore[arg-type]

    schema_a = await cache.get(1)
    schema_b = await cache.get(2)

    assert schema_a != schema_b
    assert registry.calls == 2


async def test_apply_transaction_event_forwards_the_decoded_fields() -> None:
    store = _FakeStore()
    occurred_at = datetime.now(UTC)
    record = {
        "event_id": "evt-1",
        "transaction_id": "tx-1",
        "account_id": "acct-1",
        "merchant_id": "merchant-a",
        "occurred_at": occurred_at,
    }

    await apply_transaction_event(store, record)

    assert store.calls == [("acct-1", "evt-1", "merchant-a", occurred_at)]


async def test_a_poison_message_is_logged_and_skipped_not_raised() -> None:
    """See ADR-0008: a message this consumer cannot decode or apply must not
    crash the consume loop or block every later message on its partition.

    Aggregator.start() is never called (it would need a real Kafka
    connection), and its AIOKafkaConsumer is constructed lazily there --
    see the note in consumer.py on why. _process() only needs something
    with a `commit()` on `_consumer`, so a bare stand-in is enough.
    """
    store = _FakeStore()
    aggregator = Aggregator("localhost:9092", "http://localhost:8081", store)

    commits = 0

    async def fake_commit() -> None:
        nonlocal commits
        commits += 1

    aggregator._consumer = SimpleNamespace(commit=fake_commit)

    poison_message = SimpleNamespace(
        value=b"not a valid Confluent wire-format payload",
        topic="fraudguard.transactions.v1",
        partition=0,
        offset=42,
    )

    before = _metric_value("fraudguard_aggregator_messages_total", outcome="skipped")
    before_duration_count = _metric_value(
        "fraudguard_aggregator_message_processing_duration_seconds_count"
    )

    await aggregator._process(poison_message)  # must not raise

    assert store.calls == []
    # The offset is still committed -- the poison message is skipped, not
    # retried forever.
    assert commits == 1
    # ADR-0010: a skipped message still counts, and its processing time
    # (however short) still gets observed -- both happen in _process()'s
    # `finally`, not only on the success path.
    after = _metric_value("fraudguard_aggregator_messages_total", outcome="skipped")
    assert after == before + 1.0
    after_duration_count = _metric_value(
        "fraudguard_aggregator_message_processing_duration_seconds_count"
    )
    assert after_duration_count == before_duration_count + 1.0


async def test_a_successfully_applied_message_records_the_applied_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeStore()
    aggregator = Aggregator("localhost:9092", "http://localhost:8081", store)

    commits = 0

    async def fake_commit() -> None:
        nonlocal commits
        commits += 1

    aggregator._consumer = SimpleNamespace(commit=fake_commit)

    # Bypass real schema-registry/Avro decoding (covered by
    # test_consumer_integration.py against the real stack) -- this test is
    # only about _process() recording the right metric on the success path.
    occurred_at = datetime.now(UTC)
    decoded_record = {
        "event_id": "evt-applied",
        "transaction_id": "tx-applied",
        "account_id": "acct-applied",
        "merchant_id": "merchant-applied",
        "occurred_at": occurred_at,
    }

    async def _fake_schema_lookup(schema_id: int) -> dict[str, object]:
        return {}

    monkeypatch.setattr("aggregator.consumer.schema_id_of", lambda value: 1)
    monkeypatch.setattr(aggregator._schema_cache, "get", _fake_schema_lookup)
    monkeypatch.setattr(
        "aggregator.consumer.decode", lambda schema, value: decoded_record
    )

    message = SimpleNamespace(
        value=b"irrelevant -- decode() is monkeypatched above",
        topic="fraudguard.transactions.v1",
        partition=0,
        offset=1,
    )

    before = _metric_value("fraudguard_aggregator_messages_total", outcome="applied")

    await aggregator._process(message)

    assert store.calls == [
        ("acct-applied", "evt-applied", "merchant-applied", occurred_at)
    ]
    assert commits == 1
    after = _metric_value("fraudguard_aggregator_messages_total", outcome="applied")
    assert after == before + 1.0
