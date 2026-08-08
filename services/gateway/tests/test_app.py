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


# CORS (ADR-0012): a preflight OPTIONS request is answered by CORSMiddleware
# itself, before routing -- these need no database fake with real query
# support, unlike an actual GET /v1/transactions call.


def test_cors_preflight_allows_the_configured_dashboard_origin() -> None:
    app = create_app(
        GatewaySettings(_env_file=None),
        database=_FakeDatabase(),
        events=_FakeEventPublisher(),
    )
    with TestClient(app) as client:
        response = client.options(
            "/v1/transactions",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"


def test_cors_preflight_rejects_other_origins() -> None:
    app = create_app(
        GatewaySettings(_env_file=None),
        database=_FakeDatabase(),
        events=_FakeEventPublisher(),
    )
    with TestClient(app) as client:
        response = client.options(
            "/v1/transactions",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in response.headers
