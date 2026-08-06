# ADR-0005: Database access layer

- **Status:** Accepted
- **Date:** 2026-08-07

## Context

Milestone 5 persists transactions, decisions, and labels in Postgres. Two
decisions have to be made together:

1. Which execution model the gateway uses to talk to Postgres, given it is a
   FastAPI service under a shared p99 ≤ 100 ms budget across every in-flight
   request.
2. Where the SQLAlchemy models and Alembic migrations live, given that
   Postgres is not gateway-private state — the future aggregator writes
   decisions, the future labels service writes labels, and all of them must
   agree on one schema.

## Decision

**A new workspace member, `libs/fraudguard-db`**, holds the SQLAlchemy 2.0
declarative models and an async session factory. Every service that touches
Postgres depends on it, so the schema has exactly one definition instead of
drifting per service, the same reasoning as ADR-0003 applied to a database
schema instead of a Python dependency set.

**Runtime queries are async**, via SQLAlchemy's asyncio extension over
`asyncpg`. A synchronous driver call inside an `async def` request handler
blocks the entire event loop — not just the one request — for as long as the
query takes. Under a 100 ms shared budget that is a correctness bug, not a
performance nuance.

**Alembic migrations run through a separate, synchronous driver**
(`psycopg`, v3). Alembic's autogenerate and offline-mode machinery is built
around synchronous engines; migrations are an ops-time operation invoked
from a terminal or a CI job, never from the request path, so there is no
latency budget to protect there.

**Alembic and the sync driver are kept out of every service image.** They
live in a root-level `migrate` dependency group — the same pattern as
`lint`/`typecheck`/`test` in the root `pyproject.toml` — so
`uv sync --package fraudguard-gateway` never installs a migration tool the
gateway process never calls. `fraudguard-db`'s own runtime dependencies are
only `sqlalchemy` and `asyncpg`.

## Alternatives considered

- **Models inline in `services/gateway`.** Rejected: the schema is shared
  state across services. Defining it in one service and importing it from
  others makes the gateway an accidental dependency of every service that
  touches Postgres, inverting the intended dependency direction.
- **One synchronous driver everywhere (`psycopg` for both runtime and
  migrations), avoiding a second driver dependency.** Rejected: simpler, but
  reintroduces the blocking-call-in-an-event-loop risk that `ruff`'s `ASYNC`
  lint rules exist to catch. A single request looks fine in isolation; under
  concurrent load, one blocking query stalls every other in-flight request on
  the same worker.
- **Drive Alembic from the async engine via `run_sync`, to depend on only
  `asyncpg`.** Rejected: it works, but every Alembic operation needs a
  compatibility shim for a tool that never runs from the request path in the
  first place. A plain sync engine is simpler and is what Alembic's own
  documentation and autogenerate tooling are built around.

## Consequences

**Positive**

- The gateway's `/health/ready` can now report genuine Postgres connectivity,
  since a real client exists (Milestone 4's health probes were honestly
  minimal specifically because none did yet).
- Schema changes happen in one place and are immediately visible to every
  service that depends on `fraudguard-db`.
- No service image carries a migration tool it will never invoke.

**Negative, and accepted**

- Two Postgres drivers exist in the dependency tree (`asyncpg` and
  `psycopg`), rather than one. This is treated as a feature, not a wart: they
  serve genuinely different execution contexts (request path vs. migration
  tooling) and conflating them was the alternative rejected above.
- Adding a table or column touches two places — the SQLAlchemy model in
  `fraudguard-db` and an Alembic revision in `db/migrations/` — rather than
  one. This is Alembic's normal operating model and is the price of
  migrations being reviewable and reversible instead of inferred from
  whatever the ORM currently declares.
