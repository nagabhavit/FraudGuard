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
| Transaction simulator | Not started |
| Dashboard | Not started |

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
| 12+ | Dashboard, alerts, labels, load/chaos testing, k8s/Terraform | Portfolio-polish and production-hardening milestones |

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
dashboarded in Grafana. What is not yet implemented: a *latency budget*
distinct from the timeout itself (today, "misses its budget" and "times
out" are the same bounded-timeout check, not two separate thresholds), and
alerting on a sustained fallback rate (no Alertmanager yet -- bucketed in
the 12+ milestone row alongside the dashboard/alerts work).

## Why the split ADRs live separately

Architecture decisions that are settled — the workspace layout, where
Compose lives, how quality gates are split — are recorded in
[`docs/adr/`](adr/), one immutable file per decision. This document is the
living summary; the ADRs are the record of *why*.
