"""Tests for structured JSON logging."""

from __future__ import annotations

import io
import json
import logging
from typing import Any, cast

from fraudguard_common.logging import (
    configure_logging,
    get_logger,
    request_id_var,
)
from fraudguard_common.settings import LogLevel


def _capture_one_record(
    logger_name: str, *, extra: dict[str, object] | None = None
) -> dict[str, Any]:
    configure_logging(service_name="test-service", level=LogLevel.DEBUG)
    root = logging.getLogger()
    buffer = io.StringIO()
    # Swap the handler's stream so the test can read what was emitted without
    # depending on stdout capture semantics.
    handler = cast("logging.StreamHandler[io.StringIO]", root.handlers[0])
    handler.stream = buffer

    get_logger(logger_name).info("something happened", extra=extra)

    result: dict[str, Any] = json.loads(buffer.getvalue().strip())
    return result


def test_log_line_is_valid_json_with_required_fields() -> None:
    record = _capture_one_record("fraudguard.test")
    assert record["message"] == "something happened"
    assert record["level"] == "INFO"
    assert record["logger"] == "fraudguard.test"
    assert record["service"] == "test-service"
    assert "timestamp" in record


def test_request_id_is_attached_when_bound() -> None:
    token = request_id_var.set("req-123")
    try:
        record = _capture_one_record("fraudguard.test")
    finally:
        request_id_var.reset(token)
    assert record["request_id"] == "req-123"


def test_request_id_absent_when_not_bound() -> None:
    record = _capture_one_record("fraudguard.test")
    assert "request_id" not in record


def test_extra_fields_are_included() -> None:
    record = _capture_one_record("fraudguard.test", extra={"transaction_id": "tx-1"})
    assert record["transaction_id"] == "tx-1"


def test_configure_logging_is_idempotent() -> None:
    configure_logging(service_name="test-service", level=LogLevel.INFO)
    configure_logging(service_name="test-service", level=LogLevel.INFO)
    assert len(logging.getLogger().handlers) == 1
