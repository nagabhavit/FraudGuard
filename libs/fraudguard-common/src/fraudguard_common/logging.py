"""Structured (JSON) logging shared by every FraudGuard service.

Plain-text logs are fine on a laptop and useless in production: nobody greps
a log aggregator with a regex when they could filter on a `request_id` field.
Every service configures logging through `configure_logging` once, at
startup, so every log line -- from every service -- has the same shape and
can be joined across services on `request_id`.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from fraudguard_common.settings import LogLevel

# Bound by request-scoped middleware (Milestone 4) so every log line emitted
# while handling a request carries the same correlation id, without every
# call site having to thread it through explicitly.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED_LOG_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
)


class _ServiceContextFilter(logging.Filter):
    """Stamps every record with the emitting service's name.

    A `Filter` rather than a field baked into the formatter, because the
    service name is fixed at `configure_logging` time while the formatter
    has no other reason to be constructed per-service.
    """

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service_name
        return True


class JSONFormatter(logging.Formatter):
    """Renders each `LogRecord` as one JSON object per line.

    One line per record (no multi-line JSON) so log shippers that split on
    newlines -- which is most of them -- do not fragment a single event.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id

        # Anything passed via `logger.info(..., extra={...})` rides along.
        # Reserved LogRecord attributes are excluded so we never clobber a
        # field like "message" with framework internals.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(service_name: str, level: LogLevel = LogLevel.INFO) -> None:
    """Configure the root logger for structured, single-line JSON output.

    Idempotent: safe to call more than once (tests that build the app
    factory repeatedly will), because it always replaces the handler set
    rather than appending to it.
    """
    root = logging.getLogger()
    root.setLevel(level.value)
    root.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JSONFormatter())
    handler.addFilter(_ServiceContextFilter(service_name))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a stdlib logger. Thin wrapper kept for a single import surface."""
    return logging.getLogger(name)
