# ADR-0010: Observability

- **Status:** Accepted
- **Date:** 2026-08-08

## Context

Every service now does real work -- the gateway scores transactions inline
against feature-service and model-service (ADR-0009), the aggregator
consumes Kafka and writes Redis (ADR-0008) -- but none of it is visible
except through structured logs. Logs answer "what happened to this one
request" (via `request_id`); they do not answer "what is the p99 latency
right now" or "how often is the degradation ladder's fallback rule
firing" without grepping and aggregating by hand. `docs/architecture.md`'s
own degradation-ladder section already flagged this gap explicitly:
metrics on the fallback rate were deferred to this milestone. This
milestone answers: what metrics library, where do metric definitions
live, how is cardinality kept bounded, and what gets scraped and
dashboarded.

## Decision

**`prometheus_client`, pull-based `/metrics` on every service.** The
tech stack (`README.md`) already named Prometheus/Grafana; `prometheus_client`
is the reference Python implementation, and a pull model means Prometheus
itself owns retry/backoff/storage -- no service needs a push client, a
push gateway, or its own retry logic for a metrics backend outage the way
it does for Kafka or Postgres.

**Metric *definitions* are framework-agnostic and live in
`fraudguard_common.metrics`; the `GET /metrics` HTTP route is wired
per-service.** This is the same split `fraudguard_common.errors` already
uses: the error taxonomy is shared because every service must raise the
same types, but `fraudguard_error_handler` (the FastAPI glue) is
duplicated per service (`feature_service.middleware`'s docstring already
says why: "each service owns its own small, independent copy rather than
taking on a cross-service dependency for ~60 lines"). Metric *names* and
*label sets* need the same cross-service agreement error codes do --
Grafana panels query a fixed metric name across all four services -- so
they belong in `fraudguard-common`, already a dependency of every
service. `fraudguard-common` still does not import FastAPI.

**Metric objects are module-level globals in `fraudguard_common.metrics`,
created once at import time, not inside `create_app()`.**
`prometheus_client`'s default registry raises `ValueError: Duplicated
timeseries in CollectorRegistry` if the same metric name is registered
twice, and every service's test suite calls `create_app()` once per test
-- if metric construction happened inside `create_app()`, the second test
in any file would crash the whole suite. Module-level construction mirrors
how `fraudguard_events.topics.TRANSACTIONS_V1` is already a module-level
constant, not something each caller builds.

**HTTP request labels use the route's path *template*
(`request.scope["route"].path`, e.g. `/v1/features/{account_id}`), never
the raw resolved URL, and a fixed `"unmatched"` placeholder when no route
matched (a 404).** Prometheus's own best practices call out unbounded
label cardinality as the most common way to blow up a metrics backend.
`feature-service`'s `GET /v1/features/{account_id}` takes a UUID in the
path; labelling by the raw URL would mint a new time series per account
ever queried, forever. Labelling by `"unmatched"` instead of the raw path
for 404s closes the same hole against a port scanner or a client probing
random paths.

**Two business metrics beyond generic HTTP request duration, both
directly requested by `docs/architecture.md`'s degradation-ladder
section:**
- `fraudguard_gateway_decisions_total{outcome, used_model}` -- a
  counter incremented once per `POST /v1/transactions`, `used_model`
  being `"false"` exactly when `Decision.model_version IS NULL` (the
  existing ADR-0005 fallback signal). This is the fallback-rate metric
  the degradation ladder section asked for, without adding a new signal
  distinct from the one already in Postgres.
- `fraudguard_gateway_scoring_duration_seconds` -- a histogram of
  `ScoredDecision.latency_ms` (already computed in `gateway/scoring.py`
  for the `Decision` row), against the README's p99 <= 100 ms hot-path
  budget.

  The aggregator gets the consumer-side equivalent:
  `fraudguard_aggregator_messages_total{outcome}` (`applied` or
  `skipped` -- ADR-0008's poison-message handling) and
  `fraudguard_aggregator_message_processing_duration_seconds`.

**Prometheus and Grafana join `docker-compose.yml`, scraping all four
services' `/metrics` on a 10s interval; Grafana is provisioned (datasource
+ one dashboard) as code under `ops/`, not clicked together by hand.**
`ops/prometheus/` and `ops/grafana/` already existed as reserved,
`.gitkeep`-only directories -- this milestone is what they were reserved
for. Provisioning as code means `docker compose up` produces a working
dashboard with no manual setup step, the same reason Kafka topics are
created by a script (`ops/scripts/create_kafka_topics.py`) instead of by
hand.

## Alternatives considered

- **StatsD / a push-based metrics agent.** Rejected: pull-based
  Prometheus is what the stack already committed to (README's technology
  table), and a push model adds a network dependency (the push gateway
  or StatsD daemon) to every service's hot path for a concern that should
  never be able to slow down a request.
- **OpenTelemetry metrics SDK instead of `prometheus_client` directly.**
  Rejected for now: OTel's value is a vendor-neutral pipeline (traces,
  logs, and metrics through one collector), which this project does not
  yet need -- there is one metrics backend (Prometheus) and structured
  JSON logs are already a separate, working pipeline. Revisit if a second
  metrics or tracing backend is ever added.
- **A shared `metrics_router` `APIRouter` in `fraudguard-common`,
  registered identically by every service.** Rejected to stay consistent
  with the established split: `fraudguard-common` stays framework-
  agnostic (no FastAPI import anywhere in it today), and the route itself
  is three lines duplicated four times, not a maintenance burden worth a
  new cross-service dependency.
- **Label HTTP requests by the raw resolved path.** Rejected: unbounded
  cardinality on any path with a URL parameter (`/v1/features/{account_id}`)
  -- the reason Prometheus's own documentation calls this out as the most
  common metrics-backend-killing mistake.
- **Derive the fallback rate from `Decision.model_version IS NULL` via a
  periodic Postgres query instead of a counter.** Rejected: adds a
  polling job and a database round trip for a number the gateway already
  knows the instant it makes the decision; a counter increment is free by
  comparison and has no query lag.

## Consequences

**Positive**

- Every service exposes the same metric name and label shape for HTTP
  request duration, so one Grafana panel covers all four without
  per-service query variants.
- The degradation ladder's fallback rate -- previously answerable only by
  querying Postgres for `model_version IS NULL` -- is now a live counter,
  visible in Grafana without touching the database.
- Cardinality is bounded by construction (route templates, not raw URLs),
  not by convention someone has to remember.

**Negative, and accepted**

- `fraudguard_common.metrics` now has two business metrics
  (`fraudguard_gateway_*`, `fraudguard_aggregator_*`) that only one
  service each actually records -- a small deviation from "common code is
  used by everyone," accepted because the metric *name* is the
  cross-service contract Grafana depends on, the same reasoning that
  already puts Kafka topic definitions in `fraudguard-events` even though
  only one service produces to a given topic.
- No alerting rules yet (Alertmanager, paging) -- this milestone is
  metrics and a dashboard, not on-call. Deferred to a later,
  not-yet-numbered milestone alongside the dashboard/alerts work already
  bucketed in `docs/architecture.md`'s 12+ row.
- Grafana's dashboard is provisioned with one starter dashboard (request
  latency, decision outcomes, fallback rate, aggregator throughput), not
  a comprehensive operations console -- enough to prove the pipeline
  works end to end, not a claim of production-grade dashboarding.
