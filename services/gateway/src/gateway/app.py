"""Application factory for the gateway service.

A factory rather than a module-level `app = FastAPI()` so tests can build
multiple independently-configured instances (e.g. with different settings,
or a fake database) without import-order side effects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI

from fraudguard_common.errors import FraudGuardError
from fraudguard_common.logging import configure_logging
from fraudguard_db.session import Database, LocalDatabaseSettings
from gateway import health
from gateway.errors import fraudguard_error_handler
from gateway.middleware import RequestContextMiddleware
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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await app.state.db.dispose()


def create_app(
    settings: GatewaySettings | None = None,
    database: ReadinessDependency | None = None,
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

    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(FraudGuardError, fraudguard_error_handler)
    app.include_router(health.router)

    return app
