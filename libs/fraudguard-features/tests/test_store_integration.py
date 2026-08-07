"""Integration tests against a real Redis instance.

Requires the docker compose stack (`docker compose up -d redis`), which is
why every test here is marked `integration` -- see the marker registered in
the root `pyproject.toml`. Each test uses a fresh, random account_id so
tests never collide with each other or with leftover keys from a previous
run; no cleanup is needed because every key this store writes carries a TTL
(ADR-0007).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from fraudguard_features.store import FeatureStore

pytestmark = pytest.mark.integration


@pytest.fixture
async def store() -> AsyncIterator[FeatureStore]:
    feature_store = FeatureStore()
    try:
        yield feature_store
    finally:
        await feature_store.close()


async def test_ping_succeeds_against_a_reachable_redis(store: FeatureStore) -> None:
    await store.ping()  # raises on failure; nothing to assert on success


async def test_recorded_transactions_count_toward_velocity(store: FeatureStore) -> None:
    account_id = str(uuid4())
    now = datetime.now(UTC)

    for i in range(3):
        await store.record_transaction(
            account_id, event_id=f"evt-{i}", merchant_id="merchant-a", occurred_at=now
        )

    assert await store.get_velocity(account_id, "1m", now=now) == 3
    assert await store.get_velocity(account_id, "1h", now=now) == 3
    assert await store.get_velocity(account_id, "24h", now=now) == 3


async def test_velocity_window_excludes_transactions_outside_it(
    store: FeatureStore,
) -> None:
    account_id = str(uuid4())
    now = datetime.now(UTC)

    await store.record_transaction(
        account_id,
        event_id="old",
        merchant_id="merchant-a",
        occurred_at=now - timedelta(hours=2),
    )
    await store.record_transaction(
        account_id, event_id="recent", merchant_id="merchant-a", occurred_at=now
    )

    assert await store.get_velocity(account_id, "1h", now=now) == 1
    assert await store.get_velocity(account_id, "24h", now=now) == 2


async def test_transactions_older_than_the_max_window_are_trimmed(
    store: FeatureStore,
) -> None:
    account_id = str(uuid4())
    now = datetime.now(UTC)

    await store.record_transaction(
        account_id,
        event_id="ancient",
        merchant_id="merchant-a",
        occurred_at=now - timedelta(hours=25),
    )
    await store.record_transaction(
        account_id, event_id="recent", merchant_id="merchant-a", occurred_at=now
    )

    assert await store.get_velocity(account_id, "24h", now=now) == 1


async def test_distinct_merchants_counts_unique_merchants_only(
    store: FeatureStore,
) -> None:
    account_id = str(uuid4())
    now = datetime.now(UTC)

    for merchant_id in ("merchant-a", "merchant-b", "merchant-a", "merchant-c"):
        await store.record_transaction(
            account_id, event_id=str(uuid4()), merchant_id=merchant_id, occurred_at=now
        )

    # HyperLogLog is approximate in general, but at this cardinality Redis's
    # implementation is exact in practice.
    assert await store.get_distinct_merchants(account_id, now=now) == 3


async def test_get_feature_vector_combines_velocity_and_diversity(
    store: FeatureStore,
) -> None:
    account_id = str(uuid4())
    now = datetime.now(UTC)

    await store.record_transaction(
        account_id, event_id="evt-1", merchant_id="merchant-a", occurred_at=now
    )
    await store.record_transaction(
        account_id, event_id="evt-2", merchant_id="merchant-b", occurred_at=now
    )

    vector = await store.get_feature_vector(account_id, now=now)

    assert vector == {
        "velocity_1m": 2,
        "velocity_1h": 2,
        "velocity_24h": 2,
        "distinct_merchants_24h": 2,
    }


async def test_unseen_account_has_a_zero_feature_vector(store: FeatureStore) -> None:
    account_id = str(uuid4())

    vector = await store.get_feature_vector(account_id)

    assert vector == {
        "velocity_1m": 0,
        "velocity_1h": 0,
        "velocity_24h": 0,
        "distinct_merchants_24h": 0,
    }
