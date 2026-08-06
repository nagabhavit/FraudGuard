"""Tests for the liveness and readiness endpoints.

Uses a fake database dependency rather than a real Postgres connection --
this suite must stay hermetic and pass without the docker compose stack
running. The real Postgres round trip is covered by fraudguard-db's own
integration tests (`libs/fraudguard-db/tests/test_session_integration.py`).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.settings import GatewaySettings


class _FakeDatabase:
    def __init__(self, *, healthy: bool) -> None:
        self._healthy = healthy

    async def ping(self) -> None:
        if not self._healthy:
            raise ConnectionError("postgres unreachable")

    async def dispose(self) -> None:
        pass


def _client(*, db_healthy: bool = True) -> TestClient:
    settings = GatewaySettings(_env_file=None)
    return TestClient(create_app(settings, database=_FakeDatabase(healthy=db_healthy)))


def test_liveness_reports_ok() -> None:
    response = _client().get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


def test_readiness_reports_ok_when_postgres_is_reachable() -> None:
    response = _client(db_healthy=True).get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok"}}


def test_readiness_reports_503_when_postgres_is_unreachable() -> None:
    response = _client(db_healthy=False).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"postgres": "unreachable"},
    }
