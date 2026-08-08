"""Tests for request-context middleware: request id propagation, logging,
and request-duration metrics (ADR-0010)."""

from __future__ import annotations

import io
import json
import logging
from typing import Any, cast

from fastapi.testclient import TestClient

from feature_service.app import create_app
from feature_service.settings import FeatureServiceSettings
from fraudguard_common.metrics import render_metrics


def _client() -> TestClient:
    return TestClient(create_app(FeatureServiceSettings(_env_file=None)))


def _metric_count(**labels: str) -> float:
    text = render_metrics()[0].decode()
    label_str = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    prefix = f"fraudguard_http_request_duration_seconds_count{{{label_str}}} "
    for line in text.splitlines():
        if line.startswith(prefix):
            return float(line.removeprefix(prefix))
    return 0.0


def _capture_logs() -> io.StringIO:
    buffer = io.StringIO()
    handler = cast(
        "logging.StreamHandler[io.StringIO]", logging.getLogger().handlers[0]
    )
    handler.stream = buffer
    return buffer


def test_response_carries_a_generated_request_id() -> None:
    response = _client().get("/health/live")
    assert response.headers["X-Request-Id"]


def test_caller_supplied_request_id_is_echoed_back() -> None:
    response = _client().get("/health/live", headers={"X-Request-Id": "caller-id-1"})
    assert response.headers["X-Request-Id"] == "caller-id-1"


def test_request_handled_is_logged_with_context() -> None:
    client = _client()
    buffer = _capture_logs()

    client.get("/health/live", headers={"X-Request-Id": "log-test-id"})

    # The test HTTP client (httpx2) logs its own "HTTP Request: ..." line to
    # the same root logger, so pick out ours by message rather than assuming
    # it is the last line emitted.
    records: list[dict[str, Any]] = [
        json.loads(line) for line in buffer.getvalue().splitlines() if line
    ]
    matches = [r for r in records if r["message"] == "request handled"]
    assert len(matches) == 1
    record = matches[0]
    assert record["request_id"] == "log-test-id"
    assert record["http_status"] == 200
    assert record["http_path"] == "/health/live"


def test_unhandled_exception_is_logged_as_request_failed_and_reraised() -> None:
    app = create_app(FeatureServiceSettings(_env_file=None))

    @app.get("/__test__/boom")
    async def _boom() -> None:
        raise RuntimeError("unexpected")

    client = TestClient(app, raise_server_exceptions=False)
    buffer = _capture_logs()

    client.get("/__test__/boom", headers={"X-Request-Id": "boom-id"})

    records: list[dict[str, Any]] = [
        json.loads(line) for line in buffer.getvalue().splitlines() if line
    ]
    matches = [r for r in records if r["message"] == "request failed"]
    assert len(matches) == 1
    assert matches[0]["request_id"] == "boom-id"
    assert matches[0]["http_path"] == "/__test__/boom"


def test_request_duration_is_recorded_under_the_route_template() -> None:
    labels = {
        "service": "feature-service",
        "method": "GET",
        "path": "/health/live",
        "status": "200",
    }
    client = _client()
    before = _metric_count(**labels)
    client.get("/health/live")
    after = _metric_count(**labels)
    assert after == before + 1.0


def test_unmatched_route_is_recorded_with_a_fixed_placeholder_label() -> None:
    """A client probing random paths must not mint a new label value per
    path -- see ADR-0010 on cardinality. Every 404 collapses onto the same
    "unmatched" path label regardless of what was actually requested.
    """
    labels = {
        "service": "feature-service",
        "method": "GET",
        "path": "unmatched",
        "status": "404",
    }
    client = _client()
    before = _metric_count(**labels)
    client.get("/this-path-does-not-exist-1")
    client.get("/this-path-does-not-exist-2")
    after = _metric_count(**labels)
    assert after == before + 2.0
