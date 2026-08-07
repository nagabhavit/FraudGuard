"""Tests for the application factory's lifecycle management."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from fraudguard_events import TopicSpec
from gateway.app import create_app
from gateway.settings import GatewaySettings


class _FakeDatabase:
    def __init__(self) -> None:
        self.disposed = False

    async def ping(self) -> None:
        pass

    async def dispose(self) -> None:
        self.disposed = True


class _FakeEventPublisher:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.registered_schemas: list[str] = []

    async def start(self) -> None:
        self.started = True

    async def register_schema(self, topic: TopicSpec, schema_name: str) -> None:
        self.registered_schemas.append(schema_name)

    async def publish(
        self, topic: TopicSpec, key: bytes, record: dict[str, Any]
    ) -> None:
        pass

    async def stop(self) -> None:
        self.stopped = True


def test_lifespan_disposes_the_database_on_shutdown() -> None:
    fake_db = _FakeDatabase()
    app = create_app(
        GatewaySettings(_env_file=None), database=fake_db, events=_FakeEventPublisher()
    )

    with TestClient(app) as client:
        assert fake_db.disposed is False
        client.get("/health/live")

    assert fake_db.disposed is True


def test_lifespan_starts_and_stops_the_event_publisher() -> None:
    fake_events = _FakeEventPublisher()
    app = create_app(
        GatewaySettings(_env_file=None), database=_FakeDatabase(), events=fake_events
    )

    with TestClient(app):
        assert fake_events.started is True
        assert fake_events.registered_schemas == ["transaction_received"]
        assert fake_events.stopped is False

    assert fake_events.stopped is True
