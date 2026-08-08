"""Tests for GET /metrics (ADR-0010)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

from gateway.app import create_app
from gateway.settings import GatewaySettings


def _client() -> TestClient:
    return TestClient(create_app(GatewaySettings(_env_file=None)))


def test_metrics_endpoint_returns_the_prometheus_content_type() -> None:
    response = _client().get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


def test_metrics_endpoint_exposes_the_http_request_duration_metric() -> None:
    client = _client()
    client.get("/health/live")
    response = client.get("/metrics")
    assert b"fraudguard_http_request_duration_seconds" in response.content
    assert b'service="gateway"' in response.content
