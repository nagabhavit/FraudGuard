"""Feature-service-specific settings.

Extends the shared base with the fields only this service needs. Kept in
its own module, not `app.py`, so tests can construct settings without
importing FastAPI.
"""

from __future__ import annotations

from fraudguard_common.settings import LocalDevSettings


class FeatureServiceSettings(LocalDevSettings):
    """Configuration for the feature service.

    `port` matches `FEATURE_SERVICE_PORT` in `.env.example` -- read here
    only for documentation/tooling purposes; the container's actual bind
    port is set on the `uvicorn` command in the Dockerfile, since changing
    one without the other is a common source of "it works locally" bugs.
    """

    service_name: str = "feature-service"
    port: int = 8001


def get_settings() -> FeatureServiceSettings:
    """Construct settings fresh on each call.

    Not cached (e.g. with `functools.lru_cache`) because tests routinely
    override environment variables per-test; a cached singleton would leak
    state between them.
    """
    return FeatureServiceSettings()
