"""Tests for the liveness and readiness endpoints.

Uses a fake feature-store dependency rather than a real Redis connection --
this suite must stay hermetic and pass without the docker compose stack
running. The real Redis round trip is covered by fraudguard-features' own
integration tests and by test_features_integration.py in this service.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from feature_service.app import create_app
from feature_service.settings import FeatureServiceSettings


class _FakeFeatureStore:
    def __init__(self, *, healthy: bool) -> None:
        self._healthy = healthy

    async def ping(self) -> None:
        if not self._healthy:
            raise ConnectionError("redis unreachable")

    async def get_feature_vector(self, account_id: str) -> dict[str, int]:
        raise NotImplementedError

    async def close(self) -> None:
        pass


def _client(*, store_healthy: bool = True) -> TestClient:
    settings = FeatureServiceSettings(_env_file=None)
    return TestClient(
        create_app(settings, store=_FakeFeatureStore(healthy=store_healthy))
    )


def test_liveness_reports_ok() -> None:
    response = _client().get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


def test_readiness_reports_ok_when_redis_is_reachable() -> None:
    response = _client(store_healthy=True).get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"redis": "ok"}}


def test_readiness_reports_503_when_redis_is_unreachable() -> None:
    response = _client(store_healthy=False).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "checks": {"redis": "unreachable"}}
