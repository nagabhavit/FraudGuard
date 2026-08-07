"""Model-service-specific settings.

Extends the shared base with the fields only this service needs. Kept in
its own module, not `app.py`, so tests can construct settings without
importing FastAPI.
"""

from __future__ import annotations

from fraudguard_common.settings import LocalDevSettings


class ModelServiceSettings(LocalDevSettings):
    """Configuration for the model service.

    `port` matches `MODEL_SERVICE_PORT` in `.env.example` -- read here only
    for documentation/tooling purposes; the container's actual bind port is
    set on the `uvicorn` command in the Dockerfile.

    `approve_below` / `decline_above` are the fixed cut points on
    `risk_score` (ADR-0009): below `approve_below` is `approve`, above
    `decline_above` is `decline`, between is `review`.
    """

    service_name: str = "model-service"
    port: int = 8003
    approve_below: float = 0.3
    decline_above: float = 0.7


def get_settings() -> ModelServiceSettings:
    """Construct settings fresh on each call.

    Not cached (e.g. with `functools.lru_cache`) because tests routinely
    override environment variables per-test; a cached singleton would leak
    state between them.
    """
    return ModelServiceSettings()
