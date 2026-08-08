"""Tests for GET /metrics (ADR-0010).

Uses a fake model rather than a real trained one -- this suite must stay
hermetic and pass without ml/pipelines/train.py having been run, the same
reasoning as test_model_service_health.py.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

from model_service.app import create_app
from model_service.settings import ModelServiceSettings


class _FakeModel:
    version = "fake-v1"

    def predict_proba(self, row: list[float]) -> float:
        return 0.1

    def explain(self, row: list[float], top_n: int = 3) -> list[str]:
        return []


def _client() -> TestClient:
    settings = ModelServiceSettings(_env_file=None)
    return TestClient(create_app(settings, model=_FakeModel()))


def test_metrics_endpoint_returns_the_prometheus_content_type() -> None:
    response = _client().get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


def test_metrics_endpoint_exposes_the_http_request_duration_metric() -> None:
    client = _client()
    client.get("/health/live")
    response = client.get("/metrics")
    assert b"fraudguard_http_request_duration_seconds" in response.content
    assert b'service="model-service"' in response.content
