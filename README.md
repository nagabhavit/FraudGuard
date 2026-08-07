# FraudGuard

[![CI](https://github.com/nagabhavit/fraudguard/actions/workflows/ci.yml/badge.svg)](https://github.com/nagabhavit/fraudguard/actions/workflows/ci.yml)
[![Security](https://github.com/nagabhavit/fraudguard/actions/workflows/security.yml/badge.svg)](https://github.com/nagabhavit/fraudguard/actions/workflows/security.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Distributed real-time fraud detection platform. Transactions are scored inline
in the payment authorization path against a hard budget of **p99 ≤ 100 ms**.

> **Status: early build.** Workspace, tooling, and local infrastructure are in
> place. The gateway accepts a transaction (`POST /v1/transactions`),
> persists it to Postgres, and publishes it to Kafka for the cold path —
> with no scoring logic yet. That lands with the feature store and model
> service in the milestones tracked in
> [`docs/architecture.md`](docs/architecture.md).

---

## The constraint that drives the design

FraudGuard sits inline in payment authorization — a card swipe blocks on its
answer. That produces two facts in tension:

1. **Hard latency SLA.** Exceed it and the payment processor times out and
   auto-approves, making the system decorative.
2. **Fraud signal is historical.** "Is this fraudulent?" is unanswerable from
   the transaction alone. It needs velocity, deviation from an account's
   normal behaviour, and graph signals — all of which require aggregated
   history.

You cannot compute aggregations inside 100 ms. So the core architectural move
is to **precompute features asynchronously and serve them from memory
synchronously**:

- **Hot path** — synchronous, latency-bound: gateway → feature service → model
  service → decision.
- **Cold path** — asynchronous, throughput-bound: Kafka → stream aggregator →
  Redis and Postgres → training → model registry.

Kafka is deliberately **not** in the request path. It is the durable log that
refreshes what the hot path reads. Full design: [`docs/architecture.md`](docs/architecture.md).

---

## Technology stack

| Layer | Choice | Why |
| --- | --- | --- |
| API | FastAPI | Async I/O suits a service that mostly waits on Redis and gRPC; Pydantic gives validation and OpenAPI for free |
| System of record | PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic | ACID on financial records; JSONB for feature snapshots; native partitioning; async ORM keeps the hot path off a blocking driver (ADR-0005) |
| Online store | Redis 7 | Sub-millisecond reads; sorted sets and HyperLogLog are exactly the right primitives for velocity and cardinality |
| Event log | Kafka 3.9 (KRaft) + aiokafka | Durable, replayable, ordered per key — replay is what lets features be rebuilt; async producer keeps Kafka calls off the hot path's event loop (ADR-0006) |
| Schema governance | Confluent Schema Registry + fastavro | BACKWARD compatibility enforced at the broker, not just in CI; hand-rolled wire-format codec avoids a native `librdkafka` dependency (ADR-0006) |
| Model | LightGBM | Gradient-boosted trees beat deep learning on tabular fraud data, train in minutes, infer in single-digit ms, and produce SHAP explanations regulators accept |
| Dashboard | React + TypeScript | Type safety across the API boundary |
| Packaging | uv workspace | One lockfile, per-service dependency subtrees |

---

## Prerequisites

- Docker Engine 24+ with Compose v2
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Node 20+ (dashboard, added in a later milestone)

You do **not** need a system Python 3.12. `uv` reads `.python-version` and
provisions the interpreter itself.

---

## Quick start

```bash
git clone <your-repo-url> fraudguard && cd fraudguard
cp .env.example .env

uv sync --all-packages --all-groups      # reproducible venv from uv.lock
docker compose up -d      # postgres, redis, kafka, schema registry, gateway
docker compose ps         # all five must report (healthy)

# KAFKA_AUTO_CREATE_TOPICS_ENABLE is false -- topics are created explicitly.
uv run --all-packages python ops/scripts/create_kafka_topics.py
```

Verify the stack:

```bash
docker compose exec postgres pg_isready -U fraudguard -d fraudguard
docker compose exec redis redis-cli ping
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list
curl -fsS http://localhost:8081/subjects
curl -fsS http://localhost:8000/health/live
curl -fsS http://localhost:8000/health/ready   # checks real Postgres connectivity
```

Send a transaction (persists to Postgres, publishes to Kafka -- no scoring yet):

```bash
curl -i -X POST http://localhost:8000/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{
        "account_id": "d975f45f-e13c-4934-b6bc-ed86130a8f27",
        "merchant_id": "merchant-1",
        "amount": "42.50",
        "currency": "USD",
        "occurred_at": "2026-08-07T12:00:00Z"
      }'
```

Run the gateway locally without Docker (auto-reloads on change):

```bash
uv run --package fraudguard-gateway uvicorn gateway.asgi:app --reload --port 8000
```

Tear down:

```bash
docker compose down       # stop, keep data
docker compose down -v    # stop, delete volumes
```

---

## Commands

```bash
uv sync --all-packages --all-groups                  # install everything
uv run pytest                         # tests
uv run ruff check .                   # lint
uv run ruff format .                  # format
uv run mypy .                         # type check
uv lock                               # refresh the lockfile
uv add --package fraudguard-gateway X # add a dependency to one service
```

There is intentionally no Makefile. With uv these commands are short enough
that a wrapper would add indirection without saving typing.

### Database migrations

Alembic and its driver are a dev-only `migrate` dependency group (ADR-0005) --
they never ship inside a service image, so every migration command needs
`--group migrate` explicitly:

```bash
uv run --all-packages --group migrate alembic -c db/alembic.ini upgrade head
uv run --all-packages --group migrate alembic -c db/alembic.ini downgrade -1
uv run --all-packages --group migrate alembic -c db/alembic.ini revision --autogenerate -m "message"
```

---

## Quality gates

```bash
uv run pre-commit install --install-hooks   # one-time
uv run pre-commit run --all-files           # the full local gate
```

| Check | Tool | Enforced by |
| --- | --- | --- |
| Lint and format | Ruff | pre-commit + CI |
| Static types | mypy `--strict` | pre-commit + CI |
| Tests and coverage floor | pytest, coverage | CI |
| Lockfile matches `pyproject.toml` | `uv lock --check` | pre-commit + CI |
| No committed secrets | Gitleaks | pre-commit + CI |
| Known vulnerabilities | pip-audit | CI, weekly |
| Commit message format | Conventional Commits | pre-commit |
| Workflow syntax | actionlint | pre-commit |

Branch protection on `main` requires the single aggregate check named `CI`. See
[`.github/workflows/README.md`](.github/workflows/README.md).

---

## Repository layout

```
services/     one directory per independently deployable backend service
libs/         shared python packages, imported by services
dashboard/    react operations console (npm project, not a uv member)
db/           alembic migrations and seed data
ml/           training pipelines and model artifacts (artifacts gitignored)
infra/        terraform modules and kubernetes manifests
ops/          prometheus, grafana, load tests, chaos experiments, scripts
docs/         architecture decision records and runbooks
```

**Why `src/` inside each package.** With a flat layout, `import gateway`
silently resolves to the working directory, so tests exercise the source tree
rather than the installed package and a packaging mistake only surfaces in
production. Under `src/`, that is impossible — a broken install fails loudly in
CI.

**Why a single `uv.lock` with per-member dependencies.** One resolution, one
security-scan surface, one Dependabot PR per CVE, while
`uv sync --package fraudguard-gateway` still installs only that service's
subtree. The gateway image never contains LightGBM. See
[ADR-0003](docs/adr/0003-uv-workspace-single-lockfile.md).

---

## Architecture decisions

Significant decisions are recorded in [`docs/adr/`](docs/adr/). Each states the
context, the decision, the alternatives considered, and the consequences.

| ADR | Decision |
| --- | --- |
| [0001](docs/adr/0001-record-architecture-decisions.md) | Record architecture decisions |
| [0002](docs/adr/0002-compose-file-at-repository-root.md) | Compose file at the repository root |
| [0003](docs/adr/0003-uv-workspace-single-lockfile.md) | uv workspace with a single lockfile |
| [0004](docs/adr/0004-quality-gates.md) | Split quality gates between pre-commit and CI |
| [0005](docs/adr/0005-database-access-layer.md) | Async SQLAlchemy for the app, sync Alembic for migrations, in a shared `fraudguard-db` package |
| [0006](docs/adr/0006-kafka-event-publishing.md) | aiokafka + fastavro for event publishing, in a shared `fraudguard-events` package |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for commit conventions, the ADR policy,
and the pull request checklist.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
