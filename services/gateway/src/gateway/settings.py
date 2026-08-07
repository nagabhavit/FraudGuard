"""Gateway-specific settings.

Extends the shared base with the fields only the gateway needs. Kept in its
own module, not `app.py`, so tests can construct settings without importing
FastAPI.
"""

from __future__ import annotations

from decimal import Decimal

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

    # Host-side defaults (a locally-run gateway reaching containers via their
    # published ports); docker-compose.yml overrides both to the internal
    # service names, same split as POSTGRES_HOST/REDIS_HOST.
    feature_service_url: str = "http://localhost:8001"
    model_service_url: str = "http://localhost:8003"

    # Local defaults only (ADR-0009) -- generous for docker-compose
    # networking, not tuned to the README's p99 <= 100ms budget.
    scoring_timeout_seconds: float = 2.0

    # ADR-0009's degradation-ladder fallback: above this amount -> review,
    # otherwise -> approve, used only when feature-service or model-service
    # is unreachable.
    fallback_amount_threshold: Decimal = Decimal("500.00")


def get_settings() -> GatewaySettings:
    """Construct settings fresh on each call.

    Not cached (e.g. with `functools.lru_cache`) because tests routinely
    override environment variables per-test; a cached singleton would leak
    state between them. FastAPI's dependency-injection cache scopes this to a
    single request if per-request caching is ever needed.
    """
    return GatewaySettings()
