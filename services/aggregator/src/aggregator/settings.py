"""Aggregator-specific settings.

Extends the shared base with the fields only this service needs. Kept in
its own module, not `app.py`, so tests can construct settings without
importing FastAPI.
"""

from __future__ import annotations

from fraudguard_common.settings import LocalDevSettings


class AggregatorSettings(LocalDevSettings):
    """Configuration for the stream aggregator.

    `port` matches `AGGREGATOR_PORT` in `.env.example` -- read here only for
    documentation/tooling purposes; the container's actual bind port is set
    on the `uvicorn` command in the Dockerfile, since changing one without
    the other is a common source of "it works locally" bugs. The port only
    serves `/health/*` -- this service has no business API.
    """

    service_name: str = "aggregator"
    port: int = 8002


def get_settings() -> AggregatorSettings:
    """Construct settings fresh on each call.

    Not cached (e.g. with `functools.lru_cache`) because tests routinely
    override environment variables per-test; a cached singleton would leak
    state between them.
    """
    return AggregatorSettings()
