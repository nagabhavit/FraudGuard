"""Gateway-specific settings.

Extends the shared base with the fields only the gateway needs. Kept in its
own module, not `app.py`, so tests can construct settings without importing
FastAPI.
"""

from __future__ import annotations

from fraudguard_common.settings import LocalDevSettings


class GatewaySettings(LocalDevSettings):
    """Configuration for the gateway service.

    `port` matches `GATEWAY_PORT` in `.env.example` -- the port is read here
    only for documentation/tooling purposes; the container's actual bind port
    is set on the `uvicorn` command in the Dockerfile, since changing one
    without the other is a common source of "it works locally" bugs.
    """

    service_name: str = "gateway"
    port: int = 8000


def get_settings() -> GatewaySettings:
    """Construct settings fresh on each call.

    Not cached (e.g. with `functools.lru_cache`) because tests routinely
    override environment variables per-test; a cached singleton would leak
    state between them. FastAPI's dependency-injection cache scopes this to a
    single request if per-request caching is ever needed.
    """
    return GatewaySettings()
