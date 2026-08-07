"""Liveness and readiness probes.

Readiness reports two independent checks, not one -- see ADR-0008. A
worker with no inbound requests has no natural request to fail when
something is wrong, so the background consume task exiting must be a
health signal of its own, distinct from "Redis is unreachable".
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from fraudguard_common.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["health"])

DependencyStatus = Literal["ok", "unreachable"]


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, DependencyStatus] = {}


@router.get("/health/live")
async def liveness() -> HealthStatus:
    """The process is running and able to handle a request."""
    return HealthStatus(status="ok")


@router.get("/health/ready")
async def readiness(request: Request, response: Response) -> HealthStatus:
    """The process is ready: Redis is reachable and the consume loop is alive.

    Reports 503 when either is not, so an orchestrator stops treating this
    instance as a working consumer-group member.
    """
    checks: dict[str, DependencyStatus] = {}

    try:
        await request.app.state.store.ping()
        checks["redis"] = "ok"
    except Exception:
        # A readiness probe must report a degraded dependency, never crash --
        # the exception type varies by failure mode (DNS, auth, timeout) and
        # all of them mean the same thing here: not ready.
        logger.exception("readiness check failed", extra={"dependency": "redis"})
        checks["redis"] = "unreachable"

    checks["kafka_consumer"] = (
        "ok" if request.app.state.aggregator.running else "unreachable"
    )

    if all(value == "ok" for value in checks.values()):
        return HealthStatus(status="ok", checks=checks)

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthStatus(status="degraded", checks=checks)
