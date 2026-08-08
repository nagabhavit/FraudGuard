"""Application factory for the feature service.

A factory rather than a module-level `app = FastAPI()` so tests can build
multiple independently-configured instances (e.g. with different settings,
or a fake feature store) without import-order side effects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI

from feature_service import features, health, metrics
from feature_service.errors import fraudguard_error_handler
from feature_service.middleware import RequestContextMiddleware
from feature_service.settings import FeatureServiceSettings, get_settings
from fraudguard_common.errors import FraudGuardError
from fraudguard_common.logging import configure_logging
from fraudguard_features import FeatureStore, LocalRedisSettings


class FeatureStoreDependency(Protocol):
    """What this service needs from a feature store.

    Structural rather than `fraudguard_features.FeatureStore` by name, so
    tests can substitute a fake that never opens a real Redis connection --
    this service's own test suite has no business depending on a live
    Redis; that round trip is covered by `fraudguard-features`'s own
    integration tests.
    """

    async def ping(self) -> None: ...
    async def get_feature_vector(self, account_id: str) -> dict[str, int]: ...
    async def close(self) -> None: ...


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await app.state.store.close()


def create_app(
    settings: FeatureServiceSettings | None = None,
    store: FeatureStoreDependency | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(service_name=settings.service_name, level=settings.log_level)

    app = FastAPI(
        title="FraudGuard Feature Service",
        description="Read API for precomputed fraud-detection features.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.store = store or FeatureStore(LocalRedisSettings())

    app.add_middleware(RequestContextMiddleware, service_name=settings.service_name)
    app.add_exception_handler(FraudGuardError, fraudguard_error_handler)
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(features.router)

    return app
