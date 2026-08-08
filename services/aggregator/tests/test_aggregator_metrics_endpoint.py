"""Tests for GET /metrics (ADR-0010).

Uses fake store/consumer dependencies rather than real Redis or Kafka
connections -- this suite must stay hermetic and pass without the docker
compose stack running, the same reasoning as test_aggregator_health.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

from aggregator.app import create_app
from aggregator.settings import AggregatorSettings


class _FakeStore:
    async def ping(self) -> None:
        pass

    async def record_transaction(
        self, account_id: str, event_id: str, merchant_id: str, occurred_at: datetime
    ) -> None:
        pass

    async def close(self) -> None:
        pass


class _FakeAggregator:
    running = True

    async def start(self) -> None:
        pass

    async def run_forever(self) -> None:
        pass

    async def stop(self) -> None:
        pass


def _client() -> TestClient:
    settings = AggregatorSettings(_env_file=None)
    app = create_app(settings, store=_FakeStore(), aggregator=_FakeAggregator())
    return TestClient(app)


def test_metrics_endpoint_returns_the_prometheus_content_type() -> None:
    response = _client().get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


def test_metrics_endpoint_exposes_the_http_request_duration_metric() -> None:
    client = _client()
    client.get("/health/live")
    response = client.get("/metrics")
    assert b"fraudguard_http_request_duration_seconds" in response.content
    assert b'service="aggregator"' in response.content
