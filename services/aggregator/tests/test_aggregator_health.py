"""Tests for the liveness and readiness endpoints.

Uses fake store/consumer dependencies rather than real Redis or Kafka
connections -- this suite must stay hermetic and pass without the docker
compose stack running. The real round trip is covered by
test_consumer_integration.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from aggregator.app import create_app
from aggregator.settings import AggregatorSettings


class _FakeStore:
    def __init__(self, *, healthy: bool = True) -> None:
        self._healthy = healthy

    async def ping(self) -> None:
        if not self._healthy:
            raise ConnectionError("redis unreachable")

    async def record_transaction(
        self, account_id: str, event_id: str, merchant_id: str, occurred_at: datetime
    ) -> None:
        pass

    async def close(self) -> None:
        pass


class _FakeAggregator:
    def __init__(self, *, running: bool = True) -> None:
        self.running = running

    async def start(self) -> None:
        pass

    async def run_forever(self) -> None:
        pass

    async def stop(self) -> None:
        pass


def _client(*, store_healthy: bool = True, consumer_running: bool = True) -> TestClient:
    settings = AggregatorSettings(_env_file=None)
    app = create_app(
        settings,
        store=_FakeStore(healthy=store_healthy),
        aggregator=_FakeAggregator(running=consumer_running),
    )
    return TestClient(app)


def test_liveness_reports_ok() -> None:
    response = _client().get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


def test_readiness_reports_ok_when_everything_is_healthy() -> None:
    response = _client(store_healthy=True, consumer_running=True).get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"redis": "ok", "kafka_consumer": "ok"},
    }


def test_readiness_reports_503_when_redis_is_unreachable() -> None:
    response = _client(store_healthy=False, consumer_running=True).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "unreachable"


def test_readiness_reports_503_when_the_consume_loop_has_stopped() -> None:
    response = _client(store_healthy=True, consumer_running=False).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["kafka_consumer"] == "unreachable"
