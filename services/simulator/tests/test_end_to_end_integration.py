"""Black-box end-to-end tests against the real, containerized stack. See
ADR-0011.

Unlike every other `*_integration.py` test in this repository, these make
real HTTP calls to the actual gateway and feature-service *containers*
`docker compose up` starts (`http://localhost:8000`,
`http://localhost:8001`) -- not an in-process `create_app()` + `TestClient`.
Requires the full stack running: postgres, redis, kafka, schema-registry,
gateway, aggregator, feature-service, and model-service.

Assertions are structural, not exact outcomes: CI trains a fresh model
every run (`ml/pipelines/train.py`, wired into the `integration` job since
Milestone 9), so asserting "this payload always declines" would couple this
suite to one run's randomly-trained model instead of the contract the
gateway actually promises.
"""

from __future__ import annotations

import asyncio
import time

import httpx2 as httpx
import pytest

from simulator.driver import run, send_transaction
from simulator.factory import SimulatedAccount, TransactionFactory

pytestmark = pytest.mark.integration

_GATEWAY_URL = "http://localhost:8000"
_FEATURE_SERVICE_URL = "http://localhost:8001"
_VALID_OUTCOMES = {"approve", "decline", "review"}


async def _wait_for_velocity(
    client: httpx.AsyncClient,
    account_id: str,
    at_least: int,
    timeout_seconds: float = 15.0,
) -> int:
    """Poll feature-service's real endpoint until the cold path (Kafka ->
    aggregator -> Redis) has caught up, or give up. Same shape as
    `test_consumer_integration.py`'s `_wait_for_velocity`, against the real
    container's HTTP API instead of an in-process `FeatureStore`.
    """
    deadline = time.monotonic() + timeout_seconds
    velocity = 0
    while time.monotonic() < deadline:
        response = await client.get(f"/v1/features/{account_id}")
        response.raise_for_status()
        velocity = response.json()["velocity_1m"]
        if velocity >= at_least:
            return int(velocity)
        await asyncio.sleep(0.25)
    return int(velocity)


async def test_a_batch_of_realistic_transactions_gets_valid_decisions() -> None:
    """Hot-path black-box test: post a batch of realistic transactions
    straight to the real gateway container via the driver, and check the
    response shape -- both the batch-level tally and one transaction
    inspected in full (the fields `RunSummary` doesn't retain, since its
    job is a CLI-friendly tally, not per-response detail).
    """
    factory = TransactionFactory(seed=123, account_pool_size=30)

    async with httpx.AsyncClient(base_url=_GATEWAY_URL, timeout=10.0) as client:
        summary = await run(factory, count=15, client=client)
        assert summary.sent == 15
        assert summary.failed == 0
        assert set(summary.outcomes) <= _VALID_OUTCOMES

        payload = factory.random_transaction()
        result = await send_transaction(client, payload)

    assert result["outcome"] in _VALID_OUTCOMES
    assert 0.0 <= result["risk_score"] <= 1.0
    model_version = result["model_version"]
    reason_codes = result["reason_codes"]
    if model_version is not None:
        # The real model scored this -- ADR-0009's version format, and real
        # SHAP-derived reason codes, not the fallback rule's None/None pair.
        assert model_version.startswith("fraud-lgbm-")
        assert isinstance(reason_codes, list)
        assert len(reason_codes) > 0
    else:
        assert reason_codes is None


async def test_a_burst_for_one_account_raises_its_velocity_in_feature_service() -> None:
    """Hot-and-cold-path black-box test: post several transactions for one
    account to the real gateway container, then poll the real
    feature-service container and confirm the cold path picked them up --
    the same proof `test_full_pipeline_integration.py` already makes
    in-process, now made against the actual deployed containers.
    """
    factory = TransactionFactory(seed=456)
    account = SimulatedAccount(
        account_id=factory.accounts[0].account_id, archetype="bursty"
    )
    burst_size = 6

    async with httpx.AsyncClient(base_url=_GATEWAY_URL, timeout=10.0) as gateway_client:
        for _ in range(burst_size):
            payload = factory.transaction_for(account)
            result = await send_transaction(gateway_client, payload)
            assert result["outcome"] in _VALID_OUTCOMES

    async with httpx.AsyncClient(
        base_url=_FEATURE_SERVICE_URL, timeout=10.0
    ) as feature_client:
        velocity = await _wait_for_velocity(
            feature_client, str(account.account_id), at_least=burst_size
        )

    assert velocity >= burst_size, (
        "aggregator did not apply the simulator's burst within the timeout"
    )
