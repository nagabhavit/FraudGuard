"""Translates the shared error taxonomy into HTTP responses.

One handler for the whole taxonomy, registered once in the app factory,
rather than a `try/except` in every route -- a route that forgets to catch a
domain error would otherwise leak a raw 500 with a stack trace to the caller.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from fraudguard_common.errors import FraudGuardError
from fraudguard_common.logging import get_logger

logger = get_logger(__name__)


async def fraudguard_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, FraudGuardError):
        # FastAPI's exception_handler registry is keyed by type but does not
        # narrow the handler's parameter type for us; this keeps mypy honest
        # about what actually reaches the branch below.
        raise exc

    logger.warning(
        "request rejected",
        extra={
            "error_code": exc.error_code,
            "http_path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=exc.http_status,
        content={"error_code": exc.error_code, "message": exc.message},
    )
