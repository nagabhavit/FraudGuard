"""Tests for the application factory's lifecycle management."""

from __future__ import annotations

from fastapi.testclient import TestClient

from feature_service.app import create_app
from feature_service.settings import FeatureServiceSettings


class _FakeFeatureStore:
    def __init__(self) -> None:
        self.closed = False

    async def ping(self) -> None:
        pass

    async def get_feature_vector(self, account_id: str) -> dict[str, int]:
        raise NotImplementedError

    async def close(self) -> None:
        self.closed = True


def test_lifespan_closes_the_feature_store_on_shutdown() -> None:
    fake_store = _FakeFeatureStore()
    app = create_app(FeatureServiceSettings(_env_file=None), store=fake_store)

    with TestClient(app) as client:
        assert fake_store.closed is False
        client.get("/health/live")

    assert fake_store.closed is True
