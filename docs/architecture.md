# FraudGuard architecture

## The constraint

FraudGuard sits inline in payment authorization: a card swipe blocks on its
answer. That produces a hard latency SLA — **p99 ≤ 100 ms** end to end — and a
harder problem underneath it: whether a transaction is fraudulent is not
answerable from the transaction alone. It requires velocity (how many
transactions has this card made in the last minute?), deviation from an
account's normal behaviour, and graph signals — all of which require
aggregated history that cannot be computed inside a 100 ms budget.

The resolution is to split the system into two paths with different
performance contracts:

```
Hot path  (sync,  latency-bound):  gateway -> feature service -> model service -> decision
Cold path (async, throughput-bound): kafka -> stream aggregator -> redis + postgres -> training -> model registry
```

The hot path never computes an aggregate; it only reads one that the cold
path already precomputed and placed in Redis. Kafka is deliberately **not**
in the hot path — it is the durable, replayable log that keeps the cold
path's aggregates correct, including after a bug requires rebuilding them
from scratch.

## Kafka topics

| Topic | Schema | Producer | Consumer | Key |
| --- | --- | --- | --- | --- |
| `fraudguard.transactions.v1` | `TransactionReceived` (Avro, `libs/fraudguard-events/src/fraudguard_events/schemas/`) | Gateway, on every accepted transaction | Stream aggregator (`services/aggregator`, consumer group `fraudguard-aggregator`) | `account_id` -- keeps one account's events ordered on one partition |

Declared as code in `fraudguard_events.topics`, created explicitly by
`ops/scripts/create_kafka_topics.py` (`KAFKA_AUTO_CREATE_TOPICS_ENABLE` is
`false`), and Avro-encoded with the Confluent wire format against the
Schema Registry. See ADR-0006 for the client and serialization choices, and
why a failed publish does not fail the request.

**Known gap, found via Milestone 11's real-stack testing, not yet fixed:**
"does not fail the request" is true, but a publish to a *missing* topic was
observed taking on the order of 30+ seconds to give up and log the
failure, not a bounded few milliseconds -- `aiokafka`'s own metadata-retry
behavior, not application code, is what's slow here. This does not fail
correctness (Postgres, written first, is still the system of record) but it
does mean a missing topic silently violates the hot path's p99 <= 100 ms
budget for whichever request happens to hit it, which "does not fail the
request" alone does not capture. `docker-compose.yml`'s topic-creation step
always runs before the stack is used in this project's own CI and local
workflows, so this has not been observed causing a real failure -- it is
recorded here as a known risk, not an incident.

## Feature store

| Signal | Structure | Key | Read |
| --- | --- | --- | --- |
| Velocity (1m / 1h / 24h transaction counts) | Sorted set, member = `event_id`, score = `occurred_at` | `velocity:{account_id}` | `ZCOUNT` between `now - window` and `now` |
| Merchant diversity (~24h distinct count) | HyperLogLog, one per account per calendar day | `merchant_hll:{account_id}:{date}` | `PFCOUNT` across the trailing 2 day-buckets |

`fraudguard-features` owns both the write side (`FeatureStore.record_transaction`,
called by the stream aggregator) and the read side (`get_feature_vector`,
called by `feature-service`) against the same schema. `GET /v1/features/{account_id}`
on `feature-service` returns the current vector; an account with no history
gets zeros, not 404. See ADR-0007 for the full reasoning, including why the
gateway does not call this service yet.

## Stream aggregator

`services/aggregator` consumes `fraudguard.transactions.v1`, Avro-decodes
each message against the Schema Registry (a per-process cache keyed by
schema ID avoids one registry round trip per message), and calls
`FeatureStore.record_transaction` -- closing the loop from the gateway's
`POST /v1/transactions` through Kafka to the feature store
`feature-service` reads from. Offsets commit manually, after processing,
always -- safe because the Redis writes are idempotent. A message that
cannot be decoded or applied is logged and skipped, not retried forever.
`/health/ready` reports Redis reachability and whether the consume loop is
still running, since a worker with no inbound requests has no natural
request to fail when something goes wrong. See ADR-0008 for the full
reasoning.

Verified against the real stack end to end, across genuinely separate
containers: `POST /v1/transactions` on the gateway container is visible
via `GET /v1/features/{account_id}` on the feature-service container
within seconds, with the aggregator container as the only thing connecting
them.

The hot path closes the loop: `ml/pipelines/train.py` trains a LightGBM
model on synthetic data; `model-service` loads it and serves
`POST /v1/score`; the gateway calls `feature-service` then `model-service`,
in that order, on every `POST /v1/transactions`, and persists a real
`Decision` row (ADR-0009). Verified against the real stack across four
separate containers (gateway, feature-service, model-service, and the
aggregator keeping Redis current) -- a transaction posted to the gateway
returns a genuine model decision synchronously, and the same transaction's
velocity is visible from `feature-service` a few seconds later via the
cold path.

## Observability

Every service exposes `GET /metrics` (Prometheus text format); Prometheus
scrapes all four on a 10s interval; Grafana is provisioned with a
datasource and one dashboard, both as code under `ops/` -- `docker compose
up` produces a working dashboard, no manual click-through setup (ADR-0010).

Beyond generic HTTP request-duration histograms (labelled by route
*template*, never the resolved URL -- see the ADR on cardinality), two
business metrics close gaps earlier milestones left open:
`fraudguard_gateway_decisions_total{outcome, used_model}` is the
degradation ladder's fallback-rate metric this document previously listed
as missing (`used_model="false"` is exactly the existing `Decision.model_version
IS NULL` signal, ADR-0005); `fraudguard_gateway_scoring_duration_seconds`
is the hot path's actual latency against the README's p99 <= 100 ms budget.
The aggregator gets the consumer-side equivalent:
`fraudguard_aggregator_messages_total{outcome}` and
`fraudguard_aggregator_message_processing_duration_seconds`.

Verified against the real stack: all four services show as `up` in
Prometheus's own target list, the Grafana dashboard's datasource and six
panels are provisioned and queryable, and a real `POST /v1/transactions`
is visible end to end as a PromQL query result within one scrape interval.

## Alerting

Prometheus Alertmanager (ADR-0013) joins `docker-compose.yml`, configured
as code under `ops/alertmanager/` -- the same "`docker compose up` produces
a working setup, no manual click-through" pattern ADR-0010 already
established for Prometheus and Grafana. Five rules in
`ops/prometheus/rules/fraudguard.rules.yml` (loaded via Prometheus's
`rule_files`) cover: the degradation ladder's fallback rate; a sustained
hot-path latency-budget breach rate
(`fraudguard_gateway_scoring_budget_exceeded_total`, a new metric --
distinct from the 2s `scoring_timeout_seconds` check, this is the
README's actual p99 <= 100ms budget); any of the four application services
being unreachable; the aggregator's poison-message rate (ADR-0008); and
Kafka publish failures (`fraudguard_gateway_kafka_publish_total`, a new
metric closing ADR-0006's previously log-only "persisted but never
published" gap).

Alertmanager's one receiver is a null/log receiver -- local dev, one
operator, the same posture Grafana's and the dashboard's anonymous access
already have (ADR-0010, ADR-0012). A firing alert is visible at
`http://localhost:9093` but pages no one; wiring a real notification
integration is future work for a non-local deployment.

Verified against the real stack: `docker compose up -d --build` brings up
all twelve containers healthy, including `alertmanager`; Prometheus's
`/api/v1/rules` reports all five rules loaded with no errors, and
Alertmanager's `/api/v2/alerts` reflects a rule's state change end to end
when it is forced to fire.

## Transaction simulator and end-to-end tests

`services/simulator` (ADR-0011) generates realistic transaction traffic --
a seeded pool of accounts split 90% "normal" / 10% "bursty" (the same idea
`ml/pipelines/train.py` uses for training data, applied one layer up: raw
`TransactionCreate` fields, not feature vectors) -- and sends it to a
running gateway. Generation (`TransactionFactory`) and sending (`driver`)
are separate pieces on purpose, so later load-testing work can drive the
same factory harder without a second implementation.

This is also the first milestone whose tests reach the actual *containers*
`docker compose up` starts, not an in-process `create_app()` + `TestClient`
the way every earlier integration test does. Two black-box tests in
`services/simulator/tests/test_end_to_end_integration.py`: one posts a
batch of realistic transactions straight to the real gateway container and
checks each decision's shape (a valid outcome, `risk_score` in `[0, 1]`,
`model_version` present with real reason codes exactly when the model --
not the fallback rule -- scored it); the other posts several transactions
for one account, then polls the real feature-service container until its
velocity reflects them -- the same proof the aggregator's
`test_full_pipeline_integration.py` already makes in-process, now made
against the actual deployed containers. Assertions are structural, not
exact outcomes: CI trains a fresh model every run, so pinning a test to
"this payload always declines" would couple the suite to one run's
randomly-trained model instead of the contract the gateway promises.

Verified against the real stack: `uv run --package fraudguard-simulator
python -m simulator` against the live compose stack returns real decisions
for every transaction sent; a manually-triggered burst for one account was
confirmed, by direct inspection, to raise that account's `risk_score` by
roughly two orders of magnitude once the cold path caught up, with
`reason_codes` correctly naming the velocity features responsible -- real
evidence the hot and cold paths are correctly connected, not just that
both individually run without error.

## Dashboard

`dashboard/` (ADR-0012) is a React + TypeScript ops console, outside the uv
workspace as a plain npm project (ADR-0003) with its own Dockerfile and
compose entry. It answers the question Grafana's aggregate panels
structurally cannot: "show me this account's recent transactions and why
each was scored the way it was." The gateway gains one new endpoint for
this, `GET /v1/transactions` -- paginated (`limit`/`offset`), ordered by
`occurred_at` descending, each transaction with its `Decision` embedded
(`selectinload`, one query, not one per row) -- rather than a new,
independent read service; the gateway already owns the `fraudguard-db`
session ADR-0005 built, and this read is cheap enough (indexed Postgres,
no feature-service/model-service calls) not to compete with the hot path
for either dependency.

The dashboard polls that endpoint every five seconds and renders a table:
time, account, merchant, amount, outcome, risk score, model version (or
"fallback rule" when `model_version` is null -- the same ADR-0005 signal
the degradation ladder already uses), and reason codes.

**No authentication**, the same posture Grafana already ships with
(anonymous admin access, local dev only): there is exactly one operator in
this system's only deployment target, so introducing the system's first
auth boundary here would conflate a visibility milestone with an
access-control decision that deserves its own ADR once there is a real
threat model to design against. CORS on the gateway is scoped to exactly
one origin (`GatewaySettings.dashboard_origin`, matching `DASHBOARD_PORT`),
not a wildcard.

Verified against the real stack: `docker compose up -d --build` brings up
all eleven containers healthy, including `dashboard`; a transaction posted
to the gateway is visible via `GET /v1/transactions` and in the dashboard's
own polling feed within one refresh interval; a real browser-style CORS
preflight and `GET` from the dashboard's origin both return
`Access-Control-Allow-Origin`, and a different origin gets neither.

## Labels

`libs/fraudguard-db`'s `labels` table (Milestone 5, ADR-0005) sat unused
until this milestone: nothing wrote to it. `gateway/labels.py` (ADR-0014)
closes that gap with `POST /v1/transactions/{transaction_id}/labels` --
ground truth arriving after the fact (a chargeback, a manual review, or a
customer report), on the gateway rather than a new service, for the same
reasoning ADR-0012 already applied to reads: the gateway already owns the
`fraudguard-db` session, and recording a label is a cheap, indexed insert
with no feature-service or model-service call in it, so it does not compete
with the hot path. A `transaction_id` that does not exist is a 404
(`NotFoundError`, checked before the insert, not inferred from a foreign-key
`IntegrityError`). Multiple labels per transaction are accepted with no
dedup -- a chargeback and a later manual review can disagree, and
reconciling them is a training-pipeline concern the schema was already
designed (ADR-0005) not to enforce.

`GET /v1/transactions` now embeds each transaction's labels alongside its
decision, via a second `selectinload` -- the same no-N+1 pattern ADR-0012
established, extended rather than duplicated. This is the only way an
operator sees a label was recorded; there is no dashboard UI for submitting
or browsing labels in this milestone.

**`ml/pipelines/train.py` is unchanged.** This milestone captures ground
truth; it does not consume it. A local dev stack does not accumulate enough
real `Label` rows to meaningfully retrain on, and blending real and
synthetic ground truth is deferred to a future milestone with real data to
design against.

Verified against the real stack: a posted transaction can be labeled via
`POST /v1/transactions/{id}/labels`, the label persists in Postgres and is
visible via `GET /v1/transactions`, a `transaction_id` that does not exist
returns 404, and `fraudguard_gateway_labels_total{source, is_fraud}` counts
the write.

## Current implementation status

| Component | State |
| --- | --- |
| Local infrastructure (Postgres, Redis, Kafka, Schema Registry) | Running, `docker-compose.yml` |
| `fraudguard-common` (settings, structured logging, error taxonomy) | Implemented |
| Gateway service | App factory, health probes, request-context middleware, containerized; `POST /v1/transactions` scores inline via feature-service and model-service and returns a real decision (ADR-0009) |
| Database schema / migrations | Implemented — `fraudguard-db` (SQLAlchemy models), Alembic migrations in `db/migrations/`; gateway's `/health/ready` checks real Postgres connectivity |
| Kafka topics / Avro schemas | Implemented — `fraudguard-events` (topics, schemas, Schema Registry client), `ops/scripts/create_kafka_topics.py`; gateway's `POST /v1/transactions` persists and publishes to the cold path (ADR-0006) |
| Feature store (Redis primitives) | Implemented — `fraudguard-features` (velocity sorted sets, merchant-diversity HyperLogLog); `feature-service`'s `GET /v1/features/{account_id}` serves it (ADR-0007), and the gateway calls it inline on every transaction (ADR-0009) |
| Stream aggregator | Implemented — `services/aggregator` consumes `fraudguard.transactions.v1` and maintains the Redis feature store (ADR-0008). Full cold path (gateway → Kafka → aggregator → Redis → feature-service) verified across real containers |
| Model service / LightGBM training | Implemented — `fraudguard-ml` (feature schema, model artifact, schema-hash validation), `ml/pipelines/train.py` (synthetic data, LightGBM native Booster), `model-service`'s `POST /v1/score` (reason codes via `pred_contrib`); gateway calls it inline, falling back to a fixed rule on failure (ADR-0009) |
| Observability (Prometheus/Grafana) | Implemented — `fraudguard_common.metrics` (framework-agnostic definitions), `GET /metrics` on all four services, Prometheus + Grafana in `docker-compose.yml`, dashboard and datasource provisioned as code under `ops/` (ADR-0010) |
| Alerting (Alertmanager) | Implemented — `ops/alertmanager/` (null/log receiver, ADR-0013), five rules in `ops/prometheus/rules/fraudguard.rules.yml` covering the fallback rate, a new hot-path latency-budget-exceeded metric, service health, aggregator poison messages, and a new Kafka-publish-failure metric |
| Transaction simulator | Implemented — `services/simulator` (`TransactionFactory` + `driver`, ADR-0011); black-box tests against the real, containerized gateway and feature-service (not in-process apps) verify the hot and cold paths end to end; CI's `integration` job now starts the full application tier, not just infrastructure |
| Dashboard | Implemented — `dashboard/` (React + TypeScript, npm project outside the uv workspace, ADR-0003); gateway's new `GET /v1/transactions` (ADR-0012) serves a live-polling feed of transactions and decisions, unauthenticated by design |
| Labels | Implemented — `gateway/labels.py`'s `POST /v1/transactions/{id}/labels` (ADR-0014) writes to the previously-unused `labels` table (ADR-0005); `GET /v1/transactions` embeds each transaction's labels; `ml/pipelines/train.py` still trains on synthetic data only, unchanged |

## Milestones

Numbered non-sequentially on purpose — gaps are reserved for work whose
scope is not yet fully specified.

| # | Milestone | Delivers |
| --- | --- | --- |
| 2 | `fraudguard-common` core | Settings base, structured JSON logging, typed error taxonomy |
| 4 | Gateway skeleton | FastAPI app factory, `/health/live` + `/health/ready`, request-id middleware, Dockerfile, wired into Compose |
| 5 | Database layer | SQLAlchemy models + Alembic migrations: `transactions`, `decisions`, `labels` (ADR-0005) |
| 6 | Kafka topics + schemas | Topic creation, Avro schemas in Schema Registry, gateway publishes to the cold path (ADR-0006) |
| 7 | Feature store | Redis velocity/aggregate primitives (sorted sets, HyperLogLog), a feature-service API (ADR-0007) |
| 8 | Stream aggregator | Kafka consumer maintaining Redis features from the transaction stream (ADR-0008) |
| 9 | Model service | LightGBM training on synthetic data, inference service, gateway calls it in the hot path |
| 10 | Observability | Prometheus metrics, latency histograms, a Grafana dashboard |
| 11 | Simulator + integration tests | Transaction generator, end-to-end tests against the real Compose stack |
| 12 | Dashboard | React ops console; a new gateway read endpoint, `GET /v1/transactions` (ADR-0012) |
| 13 | Alerting | Prometheus Alertmanager, alert rules for the degradation ladder and pipeline health, a hot-path latency budget distinct from the timeout (ADR-0013) |
| 14 | Labels | Gateway write endpoint for ground-truth labels arriving after the fact; embedded in the dashboard's transaction feed (ADR-0014) |
| 15+ | Load/chaos testing, k8s/Terraform | Portfolio-polish and production-hardening milestones |

## Degradation ladder

Implemented (ADR-0009). If feature-service or model-service times out,
refuses the connection, or answers with something the gateway cannot use,
the gateway falls back to a fixed rule on the transaction's own amount
(above a threshold: `review`; otherwise `approve`) rather than blocking the
payment indefinitely or failing open with no check at all. The fallback
decision is still persisted as a real `Decision` row, with
`model_version = NULL` -- the existing (Milestone 5) signal that a rule,
not the model, produced it. How often it fires is now a live metric,
`fraudguard_gateway_decisions_total{used_model="false"}` (ADR-0010),
dashboarded in Grafana, and now alertable: `FraudGuardSustainedFallbackRate`
fires when it exceeds 20% of decisions over 5 minutes (ADR-0013). The
latency budget is also now distinct from the timeout itself:
`GatewaySettings.scoring_budget_ms` (100ms, separate from the 2s
`scoring_timeout_seconds`) is checked on every scored transaction, whether
or not it fell back, and a sustained breach is its own alert,
`FraudGuardHotPathBudgetBreaches` (ADR-0013). See "Alerting" below.

## Why the split ADRs live separately

Architecture decisions that are settled — the workspace layout, where
Compose lives, how quality gates are split — are recorded in
[`docs/adr/`](adr/), one immutable file per decision. This document is the
living summary; the ADRs are the record of *why*.
