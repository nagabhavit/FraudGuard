"""Integration test for GET /v1/features/{account_id} against real Redis.

Requires the docker compose stack (`docker compose up -d redis`) -- marked
`integration` for the same reason as fraudguard-features' own integration
suite. Seeds Redis directly through FeatureStore.record_transaction (the
same write path the future stream aggregator will use, Milestone 8), then
verifies the real HTTP endpoint reads it back correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from feature_service.app import create_app
from feature_service.settings import FeatureServiceSettings
from fraudguard_features import FeatureStore

pytestmark = pytest.mark.integration


async def test_features_endpoint_reflects_real_redis_state() -> None:
    account_id = uuid4()
    now = datetime.now(UTC)

    seed_store = FeatureStore()
    try:
        await seed_store.record_transaction(
            str(account_id), event_id="evt-1", merchant_id="merchant-a", occurred_at=now
        )
        await seed_store.record_transaction(
            str(account_id), event_id="evt-2", merchant_id="merchant-b", occurred_at=now
        )
    finally:
        await seed_store.close()

    app = create_app(FeatureServiceSettings(_env_file=None))
    with TestClient(app) as client:
        response = client.get(f"/v1/features/{account_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["velocity_1m"] == 2
    assert body["velocity_1h"] == 2
    assert body["velocity_24h"] == 2
    assert body["distinct_merchants_24h"] == 2


async def test_features_endpoint_returns_zeros_for_an_unseen_account() -> None:
    account_id = uuid4()

    app = create_app(FeatureServiceSettings(_env_file=None))
    with TestClient(app) as client:
        response = client.get(f"/v1/features/{account_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["velocity_1m"] == 0
    assert body["velocity_1h"] == 0
    assert body["velocity_24h"] == 0
    assert body["distinct_merchants_24h"] == 0
