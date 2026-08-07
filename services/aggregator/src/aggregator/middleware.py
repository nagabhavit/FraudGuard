"""Request-scoped context and access logging for the aggregator's health
server.

Identical pattern to `gateway.middleware` and `feature_service.middleware`,
duplicated rather than shared -- each service owns its own small,
independent copy rather than taking on a cross-service dependency for ~60
lines.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from fraudguard_common.logging import get_logger, request_id_var

logger = get_logger(__name__)

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]

_REQUEST_ID_HEADER = "X-Request-Id"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds a request id and logs one structured line per request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        started_at = time.perf_counter()

        # The `else` clause (not code after the `try`) is what matters here:
        # it runs before `finally` resets the context var, so the success log
        # line below is still tagged with this request's id. Logging after
        # the `try` block instead would run after the reset and lose it.
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.exception(
                "request failed",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise
        else:
            duration_ms = (time.perf_counter() - started_at) * 1000
            response.headers[_REQUEST_ID_HEADER] = request_id
            logger.info(
                "request handled",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return response
        finally:
            request_id_var.reset(token)
