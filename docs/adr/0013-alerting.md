# ADR-0013: Alerting on the degradation ladder and pipeline health

- **Status:** Accepted
- **Date:** 2026-08-08

## Context

`docs/architecture.md`'s roadmap bundles four unscoped streams into one
`13+` row: "Alerts, labels, load/chaos testing, k8s/Terraform." Alerting is
the one of the four with a concrete gap already named twice elsewhere in
the docs, not just bucketed: ADR-0010's Consequences section ("No alerting
rules yet (Alertmanager, paging)... deferred to a later, not-yet-numbered
milestone") and `architecture.md`'s degradation-ladder section ("alerting
on a sustained fallback rate (no Alertmanager yet... bucketed in the 13+
milestone row's alerts work)"). Milestone 13 is that work.

Every service already exposes Prometheus metrics (ADR-0010) and Grafana
already visualizes them, but visibility still requires a human watching a
dashboard. Two of the signals worth alerting on did not exist as metrics at
all before this milestone: a publish failure to Kafka
(`gateway/transactions.py`'s `_publish_transaction_received`, ADR-0006's
accepted "persisted but never published" gap) was logged but never
counted, and "missed the README's p99 <= 100ms hot-path budget" was
indistinguishable from "timed out" -- both were the same
`scoring_timeout_seconds` (2s) check.

Five things need deciding: the alerting backend, the notification
receiver, whether to close the latency-budget gap now, whether to add the
missing Kafka-publish signal now, and what the actual alert thresholds are.

## Decision

**Prometheus Alertmanager, a new container (`prom/alertmanager`).** Added
to `docker-compose.yml` next to `prometheus`/`grafana`, configured as code
under `ops/alertmanager/` -- the same "provisioned as code, no manual
click-through" reasoning ADR-0010 already applied to Grafana. Rejected the
alternative of Grafana's built-in unified alerting specifically because
ADR-0010 already named Alertmanager as the anticipated missing piece, and
because it keeps alert routing (who gets paged) decoupled from
dashboarding (what a human looks at), consistent with this project's
pattern of one clear owner per concern.

**A null/log receiver, no real notification integration.**
`ops/alertmanager/alertmanager.yml`'s one route sends every alert to a
receiver with no Slack/email/PagerDuty configuration -- a firing alert is
visible in Alertmanager's own UI and API (`http://localhost:9093`) but
pages no one. The same posture ADR-0010 and ADR-0012 already accepted for
Grafana's and the dashboard's anonymous access: there is exactly one
operator, running `docker compose up` on their own machine, and no real
on-call to page.

**A new counter closes the latency-budget gap:
`fraudguard_gateway_scoring_budget_exceeded_total`**
(`fraudguard_common.metrics`). `GatewaySettings.scoring_budget_ms` (default
`100.0`) is a new setting, deliberately separate from the existing
`scoring_timeout_seconds` (2s) -- a request that returns well inside the
timeout can still have missed the budget, which is exactly the distinction
`architecture.md` flagged as missing. `gateway/scoring.py`'s
`_observe_scoring_latency` increments the counter on both the success path
and the fallback path (a fallback can itself take up to the timeout to
trigger, so it can miss the budget too), rather than only checking the
success path and silently missing half the cases.

**A new counter closes the Kafka-publish gap:
`fraudguard_gateway_kafka_publish_total{outcome}`**
(`fraudguard_common.metrics`). `transactions.py`'s
`_publish_transaction_received` now records `outcome="success"` or
`outcome="failure"` around the existing best-effort publish and its
existing `logger.exception` call -- the request-failure behavior ADR-0006
already decided (a publish failure still returns success, since Postgres
is the system of record) is unchanged; this only makes the already-accepted
gap observable in Prometheus instead of only in logs.

**Five alert rules, in `ops/prometheus/rules/fraudguard.rules.yml`**
(loaded via a new `rule_files` entry in `ops/prometheus/prometheus.yml`,
which also gains an `alerting.alertmanagers` block pointing at the new
container):

| Alert | Condition | For | Severity |
| --- | --- | --- | --- |
| `FraudGuardSustainedFallbackRate` | `used_model="false"` share of `fraudguard_gateway_decisions_total` > 20% | 5m | warning |
| `FraudGuardHotPathBudgetBreaches` | `fraudguard_gateway_scoring_budget_exceeded_total` share of scored transactions > 10% | 5m | warning |
| `FraudGuardServiceDown` | `up == 0` for gateway/feature-service/aggregator/model-service | 1m | critical |
| `FraudGuardAggregatorPoisonMessages` | `outcome="skipped"` share of `fraudguard_aggregator_messages_total` > 5% | 5m | warning |
| `FraudGuardKafkaPublishFailures` | `outcome="failure"` share of `fraudguard_gateway_kafka_publish_total` > 5% | 5m | warning |

Every ratio is expressed as `rate(numerator) / rate(denominator)` over the
same 5-minute window, not a fixed count, so an alert's meaning does not
depend on traffic volume and an idle stack (both rates zero, a PromQL NaN)
cannot spuriously fire. **These thresholds and durations are deliberately
illustrative, not derived from real incident history** -- this project has
none; CI trains a fresh model and the simulator drives synthetic traffic
every run (ADR-0011). They are loose enough to survive normal startup
flapping (every service briefly fails its healthcheck while dependencies
come up) but tight enough to demonstrate a real alert firing under a real
induced failure. Revisit once real traffic and a real incident history
exist to calibrate against.

## Alternatives considered

- **Grafana's built-in unified alerting instead of Alertmanager.**
  Rejected: no new container, but ADR-0010 already anticipated Alertmanager
  by name, and folding alert routing into the dashboarding tool conflates
  two concerns this project otherwise keeps separate (metrics definitions
  in `fraudguard-common`, the HTTP route per-service; topic declarations in
  `fraudguard-events`, the consumer per-service).
- **A real notification integration (Slack webhook, email, PagerDuty).**
  Rejected for the same reason ADR-0012 rejected auth for the dashboard: no
  second operator or real on-call exists yet to justify it, and it would
  mean managing a webhook URL or credentials for a local dev stack with
  nothing to protect. Revisit if this project ever has a non-local
  deployment or a second maintainer.
- **Leave "missed budget" and "timed out" conflated, alert only on the
  signals that already had metrics.** Rejected: this is the specific gap
  `architecture.md` named as the reason alerting was deferred in the first
  place; shipping an alerting milestone that still can't distinguish them
  would leave the one thing this milestone was motivated by unaddressed.
- **Alert directly on `histogram_quantile(0.99, ...)` against
  `fraudguard_gateway_scoring_duration_seconds` instead of a new counter.**
  Rejected: the default `prometheus_client` histogram buckets are not
  guaranteed fine enough near 100ms to make a quantile alert reliable, and
  a threshold-crossing counter is simpler to reason about and to test
  (`test_gateway_scoring.py`) than a bucket-interpolated quantile.
- **Infer Kafka publish failures from log volume (e.g. a log-based
  alerting rule) instead of a new metric.** Rejected: this project has no
  log-aggregation pipeline (structured JSON logs go to stdout only), and a
  Prometheus counter is one line to add and is consistent with every other
  signal this system already alerts on.
- **No thresholds yet -- ship the rules as `for: 0` visibility-only
  alerts, or don't ship rule values at all.** Rejected: `CONTRIBUTING.md`'s
  definition of done requires a documented test procedure actually
  executed, which requires a rule that can actually fire and be observed
  firing; placeholder-only rules would leave that unverifiable.

## Consequences

**Positive**

- The degradation ladder's fallback rate -- previously visible only by
  looking at a Grafana panel -- now pages (in this local setup, "shows up
  in Alertmanager's UI") on its own.
- The one gap `architecture.md` explicitly named ("misses its budget" vs.
  "times out" being the same check) is closed, with a test
  (`test_gateway_scoring.py`) proving the counter fires independently on
  both the success and fallback paths.
- ADR-0006's accepted "persisted but never published" gap is now
  observable in Prometheus, not only recoverable by a human reading logs.

**Negative, and accepted**

- A twelfth container (`docker compose ps` must now show twelve healthy
  services), and one more config file to keep in sync
  (`ops/alertmanager/alertmanager.yml`) -- accepted for the same reason
  Prometheus and Grafana were, in ADR-0010.
- Thresholds are illustrative defaults, not calibrated against real
  traffic or a real incident history, because neither exists for this
  project. Documented above as a known, accepted gap, not a claim of
  production-tuned alerting.
- The null receiver means no alert actually notifies anyone outside
  Alertmanager's own UI. Acceptable for the current single-operator, local
  deployment; must be revisited (a real receiver, and likely
  authentication ahead of it) before any shared or production deployment,
  the same caveat already attached to Grafana's and the dashboard's
  anonymous access.
