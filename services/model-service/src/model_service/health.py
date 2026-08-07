"""Liveness and readiness probes.

Unlike the gateway, feature-service, and aggregator, there is no dependency
here that can go from healthy to unhealthy after startup: the model is
loaded once, synchronously, in `create_app()` -- if that failed, the
process never came up at all (the same fail-fast choice `aggregator` makes
for a missing Kafka topic, ADR-0008; see ADR-0009 for why model-service
makes it too). Readiness always reports ok once the process is serving
traffic; the check exists for the same response shape every other
service's health endpoint has, not because there is a failure mode here to
detect.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

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
async def readiness() -> HealthStatus:
    """The process is ready: a model was loaded successfully at startup."""
    return HealthStatus(status="ok", checks={"model": "ok"})
