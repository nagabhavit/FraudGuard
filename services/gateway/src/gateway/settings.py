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

    # Milestone 27: bounds the documented gap (docs/architecture.md) where
    # a publish to a missing Kafka topic was observed taking 30+ seconds
    # (aiokafka's own metadata-retry behavior) instead of a bounded few
    # milliseconds, silently violating the hot-path budget above. Same
    # value and "generous, not budget-tuned" reasoning as
    # scoring_timeout_seconds -- this bounds the failure mode, it does not
    # claim Kafka publishes normally take anywhere near this long.
    kafka_publish_timeout_seconds: float = 2.0

    # ADR-0013: distinct from scoring_timeout_seconds above -- the README's
    # actual hot-path budget. A request that returns well inside the 2s
    # timeout can still have missed this, which is exactly the signal the
    # timeout alone cannot give the degradation ladder.
    scoring_budget_ms: float = 100.0

    # ADR-0009's degradation-ladder fallback: above this amount -> review,
    # otherwise -> approve, used only when feature-service or model-service
    # is unreachable.
    fallback_amount_threshold: Decimal = Decimal("500.00")

    # ADR-0012: the one browser origin allowed to call GET /v1/transactions.
    # Matches DASHBOARD_PORT in .env.example. Not a list -- there is exactly
    # one legitimate caller (the dashboard), and a wildcard would let any
    # page read transaction data via the browser's fetch API.
    dashboard_origin: str = "http://localhost:8080"


def get_settings() -> GatewaySettings:
    """Construct settings fresh on each call.

    Not cached (e.g. with `functools.lru_cache`) because tests routinely
    override environment variables per-test; a cached singleton would leak
    state between them. FastAPI's dependency-injection cache scopes this to a
    single request if per-request caching is ever needed.
    """
    return GatewaySettings()
