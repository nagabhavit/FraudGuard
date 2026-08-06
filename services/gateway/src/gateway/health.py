"""Liveness and readiness probes.

Deliberately minimal at this milestone: the gateway does not yet hold a
Postgres, Redis, or Kafka client (those arrive with their own milestones and
their own dependency decisions), so `/health/ready` cannot honestly report on
them yet. It reports only what is true right now -- that the process started
and its configuration loaded -- rather than fake a downstream check.
Milestone 5+ extends `checks` as each dependency is wired in.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok"]
    checks: dict[str, Literal["ok"]] = {}


@router.get("/health/live")
async def liveness() -> HealthStatus:
    """The process is running and able to handle a request."""
    return HealthStatus(status="ok")


@router.get("/health/ready")
async def readiness() -> HealthStatus:
    """The process is ready to serve traffic.

    No downstream dependency checks are registered yet -- see module
    docstring. An orchestrator polling this endpoint today gets the same
    signal as `/health/live`; that is honest, not a placeholder pretending to
    be more than it is.
    """
    return HealthStatus(status="ok")
