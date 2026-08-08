"""Application factory for the gateway service.

A factory rather than a module-level `app = FastAPI()` so tests can build
multiple independently-configured instances (e.g. with different settings,
or fake dependencies) without import-order side effects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fraudguard_common.errors import FraudGuardError
from fraudguard_common.logging import configure_logging
from fraudguard_db.session import Database, LocalDatabaseSettings
from fraudguard_events import (
    TRANSACTIONS_V1,
    EventProducer,
    LocalEventSettings,
    TopicSpec,
)
from gateway import health, metrics, transactions
from gateway.errors import fraudguard_error_handler
from gateway.middleware import RequestContextMiddleware
from gateway.scoring import HttpScoringClient, ScoringDependency
from gateway.settings import GatewaySettings, get_settings


class ReadinessDependency(Protocol):
    """What `/health/ready` needs from a dependency.

    Structural rather than `fraudguard_db.session.Database` by name, so
    tests can substitute a fake that never opens a real Postgres connection
    -- the gateway's own test suite has no business depending on a live
    database; that round trip is covered by `fraudguard-db`'s own
    integration tests.
    """

    async def ping(self) -> None: ...
    async def dispose(self) -> None: ...


class EventPublisher(Protocol):
    """What the gateway needs from an event producer.

    Structural for the same reason as `ReadinessDependency`: tests can
    substitute a fake that never opens a real Kafka connection. The real
    round trip is covered by the `integration`-marked tests in
    `services/gateway/tests/test_transactions_integration.py`.
    """

    async def start(self) -> None: ...
    async def register_schema(self, topic: TopicSpec, schema_name: str) -> None: ...
    async def publish(
        self, topic: TopicSpec, key: bytes, record: dict[str, Any]
    ) -> None: ...
    async def stop(self) -> None: ...


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    await app.state.events.start()
    await app.state.events.register_schema(TRANSACTIONS_V1, "transaction_received")
    try:
        yield
    finally:
        await app.state.db.dispose()
        await app.state.events.stop()
        await app.state.scoring.aclose()


def create_app(
    settings: GatewaySettings | None = None,
    database: ReadinessDependency | None = None,
    events: EventPublisher | None = None,
    scoring: ScoringDependency | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(service_name=settings.service_name, level=settings.log_level)

    app = FastAPI(
        title="FraudGuard Gateway",
        description="Transaction authorization gateway and hot-path orchestrator.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.db = database or Database(LocalDatabaseSettings())
    if events is not None:
        app.state.events = events
    else:
        event_settings = LocalEventSettings()
        app.state.events = EventProducer(
            event_settings.kafka_bootstrap_servers, event_settings.schema_registry_url
        )
    app.state.scoring = scoring or HttpScoringClient(
        feature_service_url=settings.feature_service_url,
        model_service_url=settings.model_service_url,
        timeout_seconds=settings.scoring_timeout_seconds,
    )

    app.add_middleware(RequestContextMiddleware, service_name=settings.service_name)
    # ADR-0012: only the dashboard's own origin, only GET -- it is the one
    # legitimate browser caller of this API, and the only route it calls is
    # the read-only transaction feed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.dashboard_origin],
        allow_methods=["GET"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.add_exception_handler(FraudGuardError, fraudguard_error_handler)
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(transactions.router)

    return app
