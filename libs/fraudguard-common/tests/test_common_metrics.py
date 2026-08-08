"""Tests for the shared Prometheus metrics (ADR-0010).

Metric objects are process-global (`prometheus_client`'s default registry),
and the full test suite runs in one process -- other test files exercising
gateway/aggregator code paths increment the same counters this file reads.
Assertions here are always *deltas* (value after an action minus value
before it), never absolute values, so this file's outcome does not depend
on what else has run in this process.

Reads through `render_metrics()` -- the same public surface a real
`GET /metrics` endpoint serves -- rather than `prometheus_client`'s private
per-sample attributes, so these tests exercise exactly what production code
exposes.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST

from fraudguard_common.metrics import (
    observe_aggregator_processing_duration,
    observe_gateway_scoring_duration,
    observe_http_request,
    record_aggregator_message,
    record_gateway_decision,
    render_metrics,
)


def _sample_value(rendered: bytes, metric_name: str, **labels: str) -> float:
    text = rendered.decode()
    label_str = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    prefix = f"{metric_name}{{{label_str}}} " if labels else f"{metric_name} "
    for line in text.splitlines():
        if line.startswith(prefix):
            return float(line.removeprefix(prefix))
    return 0.0


def test_render_metrics_returns_the_prometheus_content_type() -> None:
    _, content_type = render_metrics()
    assert content_type == CONTENT_TYPE_LATEST


def test_render_metrics_returns_bytes_containing_known_metric_names() -> None:
    body, _ = render_metrics()
    assert b"fraudguard_http_request_duration_seconds" in body
    assert b"fraudguard_gateway_decisions_total" in body
    assert b"fraudguard_gateway_scoring_duration_seconds" in body
    assert b"fraudguard_aggregator_messages_total" in body


def test_observe_http_request_records_under_the_given_labels() -> None:
    labels = {
        "service": "test-metrics-service",
        "method": "GET",
        "path": "/v1/widgets/{id}",
        "status": "200",
    }
    before = _sample_value(
        render_metrics()[0], "fraudguard_http_request_duration_seconds_count", **labels
    )
    observe_http_request(
        service="test-metrics-service",
        method="GET",
        path="/v1/widgets/{id}",
        status_code=200,
        duration_seconds=0.05,
    )
    after = _sample_value(
        render_metrics()[0], "fraudguard_http_request_duration_seconds_count", **labels
    )
    assert after == before + 1.0


def test_record_gateway_decision_marks_used_model_true_when_a_model_scored_it() -> None:
    labels = {"outcome": "approve", "used_model": "true"}
    before = _sample_value(
        render_metrics()[0], "fraudguard_gateway_decisions_total", **labels
    )
    record_gateway_decision(outcome="approve", model_version="fraud-lgbm-test")
    after = _sample_value(
        render_metrics()[0], "fraudguard_gateway_decisions_total", **labels
    )
    assert after == before + 1.0


def test_record_gateway_decision_marks_used_model_false_on_fallback() -> None:
    labels = {"outcome": "review", "used_model": "false"}
    before = _sample_value(
        render_metrics()[0], "fraudguard_gateway_decisions_total", **labels
    )
    record_gateway_decision(outcome="review", model_version=None)
    after = _sample_value(
        render_metrics()[0], "fraudguard_gateway_decisions_total", **labels
    )
    assert after == before + 1.0


def test_observe_gateway_scoring_duration_increments_the_histogram_count() -> None:
    before = _sample_value(
        render_metrics()[0], "fraudguard_gateway_scoring_duration_seconds_count"
    )
    observe_gateway_scoring_duration(0.012)
    after = _sample_value(
        render_metrics()[0], "fraudguard_gateway_scoring_duration_seconds_count"
    )
    assert after == before + 1.0


def test_record_aggregator_message_counts_by_outcome() -> None:
    labels = {"outcome": "applied"}
    before = _sample_value(
        render_metrics()[0], "fraudguard_aggregator_messages_total", **labels
    )
    record_aggregator_message(outcome="applied")
    after = _sample_value(
        render_metrics()[0], "fraudguard_aggregator_messages_total", **labels
    )
    assert after == before + 1.0


def test_observe_aggregator_processing_duration_increments_the_histogram_count() -> (
    None
):
    before = _sample_value(
        render_metrics()[0],
        "fraudguard_aggregator_message_processing_duration_seconds_count",
    )
    observe_aggregator_processing_duration(0.003)
    after = _sample_value(
        render_metrics()[0],
        "fraudguard_aggregator_message_processing_duration_seconds_count",
    )
    assert after == before + 1.0
