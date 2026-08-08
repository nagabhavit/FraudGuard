"""Application factory for the stream aggregator.

A factory rather than a module-level `app = FastAPI()` so tests can build
multiple independently-configured instances (e.g. with different settings,
or fake dependencies) without import-order side effects.

Unlike the gateway and feature-service, this process's real work is not
handling HTTP requests -- it is the background Kafka consume loop
(`aggregator.consumer.Aggregator.run_forever`). The FastAPI app exists only
to expose `/health/*`; see ADR-0008 for why a worker still gets a health
server rather than none at all.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Protocol

from fastapi import FastAPI

from aggregator import health, metrics
from aggregator.consumer import Aggregator
from aggregator.middleware import RequestContextMiddleware
from aggregator.settings import AggregatorSettings, get_settings
from fraudguard_common.logging import configure_logging
from fraudguard_events import LocalEventSettings
from fraudguard_features import FeatureStore, LocalRedisSettings


class FeatureStoreDependency(Protocol):
    """What this service needs from a feature store: the readiness check
    (`ping`) and the write side the consume loop applies each event to
    (`record_transaction`).

    Structural rather than `fraudguard_features.FeatureStore` by name, so
    tests can substitute a fake that never opens a real Redis connection --
    the real round trip is covered by this service's integration tests.
    """

    async def ping(self) -> None: ...
    async def record_transaction(
        self,
        account_id: str,
        event_id: str,
        merchant_id: str,
        occurred_at: datetime,
    ) -> None: ...
    async def close(self) -> None: ...


class ConsumerDependency(Protocol):
    """What `/health/ready` and the lifespan need from the consumer.

    Structural rather than `aggregator.consumer.Aggregator` by name, so
    tests can substitute a fake that never opens a real Kafka connection.
    """

    running: bool

    async def start(self) -> None: ...
    async def run_forever(self) -> None: ...
    async def stop(self) -> None: ...


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    await app.state.aggregator.start()
    consume_task = asyncio.create_task(app.state.aggregator.run_forever())
    try:
        yield
    finally:
        consume_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consume_task
        await app.state.aggregator.stop()
        await app.state.store.close()


def create_app(
    settings: AggregatorSettings | None = None,
    store: FeatureStoreDependency | None = None,
    aggregator: ConsumerDependency | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(service_name=settings.service_name, level=settings.log_level)

    app = FastAPI(
        title="FraudGuard Stream Aggregator",
        description="Kafka consumer that maintains the Redis feature store.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.store = store or FeatureStore(LocalRedisSettings())

    if aggregator is not None:
        app.state.aggregator = aggregator
    else:
        event_settings = LocalEventSettings()
        app.state.aggregator = Aggregator(
            event_settings.kafka_bootstrap_servers,
            event_settings.schema_registry_url,
            app.state.store,
        )

    app.add_middleware(RequestContextMiddleware, service_name=settings.service_name)
    app.include_router(health.router)
    app.include_router(metrics.router)

    return app
