"""Tests for the application factory's lifecycle management."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.settings import GatewaySettings


class _FakeDatabase:
    def __init__(self) -> None:
        self.disposed = False

    async def ping(self) -> None:
        pass

    async def dispose(self) -> None:
        self.disposed = True


def test_lifespan_disposes_the_database_on_shutdown() -> None:
    fake_db = _FakeDatabase()
    app = create_app(GatewaySettings(_env_file=None), database=fake_db)

    with TestClient(app) as client:
        assert fake_db.disposed is False
        client.get("/health/live")

    assert fake_db.disposed is True
