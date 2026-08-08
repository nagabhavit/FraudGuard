"""Prometheus metrics shared by every FraudGuard service. See ADR-0010.

Framework-agnostic -- no FastAPI import here, the same split
`fraudguard_common.errors` already uses: metric *names* and *label sets*
need cross-service agreement (a Grafana panel queries one name across all
four services), so they live here; the `GET /metrics` HTTP route itself is
three lines duplicated per service, the same way `fraudguard_error_handler`
is.

Every metric below is a module-level object, constructed once at import
time. `prometheus_client`'s default registry raises `ValueError:
Duplicated timeseries` if the same metric name is registered twice, and
every service's test suite calls `create_app()` once per test -- metric
construction cannot live inside `create_app()` without the second test in
any file crashing the whole run.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

#: Path label is the route's *template* (e.g. "/v1/features/{account_id}"),
#: never the resolved URL -- see ADR-0010 on cardinality. Callers unable to
#: resolve a route (a 404) must pass "unmatched", not the raw path.
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "fraudguard_http_request_duration_seconds",
    "HTTP request duration in seconds, by service, method, route, and status.",
    labelnames=("service", "method", "path", "status"),
)

#: The degradation ladder's fallback rate (ADR-0009): used_model is "false"
#: exactly when Decision.model_version IS NULL, the existing ADR-0005 signal
#: that a fallback rule, not the model, produced the decision.
GATEWAY_DECISIONS_TOTAL = Counter(
    "fraudguard_gateway_decisions_total",
    "Transaction decisions, by outcome and whether a model (vs. a fallback) scored it.",
    labelnames=("outcome", "used_model"),
)

#: The hot path's actual scoring latency (feature-service + model-service),
#: against the README's p99 <= 100ms budget.
GATEWAY_SCORING_DURATION_SECONDS = Histogram(
    "fraudguard_gateway_scoring_duration_seconds",
    "Time spent scoring one transaction against feature-service and model-service.",
)

#: ADR-0013: distinct from the hard timeout (`scoring_timeout_seconds`,
#: currently 2s) -- a request that comes back well inside the timeout can
#: still have missed the README's p99 <= 100ms hot-path budget. This counts
#: every transaction whose scoring latency exceeded that budget, whether or
#: not it ultimately timed out, so a sustained budget miss is alertable
#: separately from an outright dependency failure.
GATEWAY_SCORING_BUDGET_EXCEEDED_TOTAL = Counter(
    "fraudguard_gateway_scoring_budget_exceeded_total",
    "Transactions whose scoring latency exceeded the hot-path budget.",
)

#: ADR-0006's accepted gap made concrete: a transaction can be durably
#: persisted in Postgres without ever reaching Kafka if the publish fails.
#: That gap previously produced only a log line -- this is the counter that
#: makes it alertable (ADR-0013).
GATEWAY_KAFKA_PUBLISH_TOTAL = Counter(
    "fraudguard_gateway_kafka_publish_total",
    "TransactionReceived publishes to Kafka, by outcome.",
    labelnames=("outcome",),
)

#: ADR-0008's poison-message handling: "skipped" means a message was
#: decoded-but-failed or undecodable and was logged and skipped, not retried.
AGGREGATOR_MESSAGES_TOTAL = Counter(
    "fraudguard_aggregator_messages_total",
    "Kafka messages the aggregator has processed, by outcome.",
    labelnames=("outcome",),
)

AGGREGATOR_MESSAGE_PROCESSING_DURATION_SECONDS = Histogram(
    "fraudguard_aggregator_message_processing_duration_seconds",
    "Time spent decoding and applying one Kafka message to the feature store.",
)


def observe_http_request(
    *, service: str, method: str, path: str, status_code: int, duration_seconds: float
) -> None:
    HTTP_REQUEST_DURATION_SECONDS.labels(
        service=service, method=method, path=path, status=str(status_code)
    ).observe(duration_seconds)


def record_gateway_decision(*, outcome: str, model_version: str | None) -> None:
    used_model = "true" if model_version is not None else "false"
    GATEWAY_DECISIONS_TOTAL.labels(outcome=outcome, used_model=used_model).inc()


def observe_gateway_scoring_duration(duration_seconds: float) -> None:
    GATEWAY_SCORING_DURATION_SECONDS.observe(duration_seconds)


def record_gateway_scoring_budget_exceeded() -> None:
    GATEWAY_SCORING_BUDGET_EXCEEDED_TOTAL.inc()


def record_gateway_kafka_publish(*, outcome: str) -> None:
    GATEWAY_KAFKA_PUBLISH_TOTAL.labels(outcome=outcome).inc()


def record_aggregator_message(*, outcome: str) -> None:
    AGGREGATOR_MESSAGES_TOTAL.labels(outcome=outcome).inc()


def observe_aggregator_processing_duration(duration_seconds: float) -> None:
    AGGREGATOR_MESSAGE_PROCESSING_DURATION_SECONDS.observe(duration_seconds)


def render_metrics() -> tuple[bytes, str]:
    """The current snapshot, ready to hand back as an HTTP response body."""
    return generate_latest(), CONTENT_TYPE_LATEST
