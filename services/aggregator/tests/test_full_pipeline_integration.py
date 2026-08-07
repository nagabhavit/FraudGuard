"""End-to-end test of the whole cold path this milestone completes:

    gateway (POST /v1/transactions) -> Kafka -> aggregator -> Redis -> feature-service

Requires the docker compose stack (postgres, kafka, schema-registry, redis)
-- marked `integration`. This is the test that proves Milestones 6, 7, and
8 actually compose into the pipeline docs/architecture.md describes, not
just that each service works in isolation.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aggregator.consumer import Aggregator
from feature_service.app import create_app as create_feature_service_app
from feature_service.settings import FeatureServiceSettings
from fraudguard_features import FeatureStore
from gateway.app import create_app as create_gateway_app
from gateway.settings import GatewaySettings

pytestmark = pytest.mark.integration

_KAFKA_BOOTSTRAP_SERVERS = "localhost:29092"
_SCHEMA_REGISTRY_URL = "http://localhost:8081"


async def _wait_until(
    condition: Callable[[], Awaitable[bool]], timeout_seconds: float = 15.0
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if await condition():
            return True
        await asyncio.sleep(0.25)
    return False


async def test_transaction_flows_from_gateway_through_to_feature_service() -> None:
    account_id = uuid4()
    store = FeatureStore()
    aggregator = Aggregator(
        _KAFKA_BOOTSTRAP_SERVERS,
        _SCHEMA_REGISTRY_URL,
        store,
        group_id=f"test-full-pipeline-{uuid4()}",
    )

    consume_task: asyncio.Task[None] | None = None
    try:
        await aggregator.start()
        consume_task = asyncio.create_task(aggregator.run_forever())

        gateway_app = create_gateway_app(GatewaySettings(_env_file=None))
        with TestClient(gateway_app) as gateway_client:
            response = gateway_client.post(
                "/v1/transactions",
                json={
                    "account_id": str(account_id),
                    "merchant_id": "merchant-pipeline-test",
                    "amount": "5.00",
                    "currency": "USD",
                    # A real "now", not a fixed clock time -- the 1-minute
                    # velocity window this test asserts on is relative to
                    # wall-clock time when the test runs, not to any
                    # particular date.
                    "occurred_at": datetime.now(UTC).isoformat(),
                },
            )
        assert response.status_code == 202

        async def _velocity_recorded() -> bool:
            return await store.get_velocity(str(account_id), "1m") > 0

        assert await _wait_until(_velocity_recorded), (
            "aggregator did not apply the gateway's transaction within the timeout"
        )

        feature_service_app = create_feature_service_app(
            FeatureServiceSettings(_env_file=None)
        )
        with TestClient(feature_service_app) as feature_client:
            features_response = feature_client.get(f"/v1/features/{account_id}")

        assert features_response.status_code == 200
        body = features_response.json()
        assert body["velocity_1m"] == 1
        assert body["distinct_merchants_24h"] == 1
    finally:
        if consume_task is not None:
            consume_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consume_task
        await aggregator.stop()
        await store.close()
