"""Application factory for the model service.

A factory rather than a module-level `app = FastAPI()` so tests can build
multiple independently-configured instances (e.g. with different settings,
or a fake model) without import-order side effects.

No lifespan context here, unlike the gateway, feature-service, and
aggregator: there is no async resource to start or dispose. Loading the
model is synchronous and happens once, directly in `create_app()` -- if it
fails (no trained model on disk), the exception propagates out of
`create_app()` and the process never comes up, the same fail-fast choice
`aggregator` makes for a missing Kafka topic (ADR-0008, ADR-0009).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from fastapi import FastAPI

from fraudguard_common.errors import FraudGuardError
from fraudguard_common.logging import configure_logging
from fraudguard_ml import FraudModel, LocalModelArtifactSettings
from model_service import health, scoring
from model_service.errors import fraudguard_error_handler
from model_service.middleware import RequestContextMiddleware
from model_service.settings import ModelServiceSettings, get_settings


class FraudModelDependency(Protocol):
    """What this service needs from a model.

    Structural rather than `fraudguard_ml.FraudModel` by name, so tests can
    substitute a fake that needs no trained model file on disk -- the real
    artifact (training, saving, loading, schema-hash validation) is covered
    by `fraudguard-ml`'s own test suite and by this service's integration
    test against the real, trained model.
    """

    version: str

    def predict_proba(self, row: list[float]) -> float: ...
    def explain(self, row: list[float], top_n: int = 3) -> list[str]: ...


def create_app(
    settings: ModelServiceSettings | None = None,
    model: FraudModelDependency | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(service_name=settings.service_name, level=settings.log_level)

    app = FastAPI(
        title="FraudGuard Model Service",
        description="Real-time fraud scoring over a trained LightGBM model.",
        version="0.1.0",
    )
    app.state.settings = settings

    if model is not None:
        app.state.model = model
    else:
        artifact_settings = LocalModelArtifactSettings()
        app.state.model = FraudModel.load(
            Path(artifact_settings.model_path),
            Path(artifact_settings.model_metadata_path),
        )

    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(FraudGuardError, fraudguard_error_handler)
    app.include_router(health.router)
    app.include_router(scoring.router)

    return app
