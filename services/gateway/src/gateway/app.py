"""Application factory for the gateway service.

A factory rather than a module-level `app = FastAPI()` so tests can build
multiple independently-configured instances (e.g. with different settings)
without import-order side effects.
"""

from __future__ import annotations

from fastapi import FastAPI

from fraudguard_common.errors import FraudGuardError
from fraudguard_common.logging import configure_logging
from gateway import health
from gateway.errors import fraudguard_error_handler
from gateway.middleware import RequestContextMiddleware
from gateway.settings import GatewaySettings, get_settings


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(service_name=settings.service_name, level=settings.log_level)

    app = FastAPI(
        title="FraudGuard Gateway",
        description="Transaction authorization gateway and hot-path orchestrator.",
        version="0.1.0",
    )
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(FraudGuardError, fraudguard_error_handler)
    app.include_router(health.router)

    return app
