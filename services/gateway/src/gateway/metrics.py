"""Prometheus scrape endpoint. See ADR-0010.

Metric definitions and rendering are framework-agnostic
(`fraudguard_common.metrics`); this route is the thin, per-service FastAPI
wiring around it, the same split `errors.py`'s `fraudguard_error_handler`
already uses for the shared error taxonomy.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from fraudguard_common.metrics import render_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def get_metrics() -> Response:
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
