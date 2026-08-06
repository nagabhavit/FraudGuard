"""Tests for the liveness and readiness endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.settings import GatewaySettings


def _client() -> TestClient:
    settings = GatewaySettings(_env_file=None)
    return TestClient(create_app(settings))


def test_liveness_reports_ok() -> None:
    response = _client().get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


def test_readiness_reports_ok() -> None:
    response = _client().get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}
