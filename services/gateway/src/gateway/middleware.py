"""Request-scoped context, access logging, and request metrics for the gateway.

Every request gets a request id (reused from the `X-Request-Id` header if
the caller -- typically an upstream load balancer -- already set one, so a
single transaction keeps one id across hops). The id is bound to
`fraudguard_common.logging.request_id_var` for the lifetime of the request,
so every log line emitted while handling it, from any module, carries it
without threading it through function signatures.

Also records `fraudguard_http_request_duration_seconds` (ADR-0010) for every
request, labelled by the route's path *template*
(`request.scope["route"].path`, e.g. "/v1/transactions"), never the resolved
URL -- an unmatched route (a 404) is labelled "unmatched" instead of the raw
path, so a client probing random paths cannot mint unbounded label
cardinality either way.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from fraudguard_common.logging import get_logger, request_id_var
from fraudguard_common.metrics import observe_http_request

logger = get_logger(__name__)

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]

_REQUEST_ID_HEADER = "X-Request-Id"
_UNMATCHED_PATH = "unmatched"


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else _UNMATCHED_PATH


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds a request id, logs one structured line per request, and
    records its duration as a Prometheus observation."""

    def __init__(self, app: ASGIApp, *, service_name: str) -> None:
        super().__init__(app)
        self._service_name = service_name

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
            duration_seconds = time.perf_counter() - started_at
            logger.exception(
                "request failed",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "duration_ms": round(duration_seconds * 1000, 2),
                },
            )
            observe_http_request(
                service=self._service_name,
                method=request.method,
                path=_route_path(request),
                status_code=500,
                duration_seconds=duration_seconds,
            )
            raise
        else:
            duration_seconds = time.perf_counter() - started_at
            response.headers[_REQUEST_ID_HEADER] = request_id
            logger.info(
                "request handled",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": response.status_code,
                    "duration_ms": round(duration_seconds * 1000, 2),
                },
            )
            observe_http_request(
                service=self._service_name,
                method=request.method,
                path=_route_path(request),
                status_code=response.status_code,
                duration_seconds=duration_seconds,
            )
            return response
        finally:
            request_id_var.reset(token)
