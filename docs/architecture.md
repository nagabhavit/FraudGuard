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

## Current implementation status

| Component | State |
| --- | --- |
| Local infrastructure (Postgres, Redis, Kafka, Schema Registry) | Running, `docker-compose.yml` |
| `fraudguard-common` (settings, structured logging, error taxonomy) | Implemented |
| Gateway service | App factory, health probes, request-context middleware, containerized — no scoring logic yet |
| Database schema / migrations | Implemented — `fraudguard-db` (SQLAlchemy models), Alembic migrations in `db/migrations/`; gateway's `/health/ready` checks real Postgres connectivity |
| Kafka topics / Avro schemas | Not started |
| Feature store (Redis primitives) | Not started |
| Stream aggregator | Not started |
| Model service / LightGBM training | Not started |
| Observability (Prometheus/Grafana) | Not started |
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
| 6 | Kafka topics + schemas | Topic creation, Avro schemas in Schema Registry, gateway publishes to the cold path |
| 7 | Feature store | Redis velocity/aggregate primitives (sorted sets, HyperLogLog), a feature-service API |
| 8 | Stream aggregator | Kafka consumer maintaining Redis features from the transaction stream |
| 9 | Model service | LightGBM training on synthetic data, inference service, gateway calls it in the hot path |
| 10 | Observability | Prometheus metrics, latency histograms, a Grafana dashboard |
| 11 | Simulator + integration tests | Transaction generator, end-to-end tests against the real Compose stack |
| 12+ | Dashboard, alerts, labels, degradation ladder, load/chaos testing, k8s/Terraform | Portfolio-polish and production-hardening milestones |

## Degradation ladder

Not yet implemented (arrives with the feature store and model service, since
there is nothing to degrade from until those exist). The intended shape:
if the feature service or model service misses its latency budget, the
gateway falls back to a cheaper, rule-based score rather than blocking the
payment indefinitely or failing open with no check at all. Recorded as its
own ADR once the model service exists to fall back from.

## Why the split ADRs live separately

Architecture decisions that are settled — the workspace layout, where
Compose lives, how quality gates are split — are recorded in
[`docs/adr/`](adr/), one immutable file per decision. This document is the
living summary; the ADRs are the record of *why*.
