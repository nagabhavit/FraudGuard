# ADR-0012: Dashboard read API on the gateway, unauthenticated

- **Status:** Accepted
- **Date:** 2026-08-08

## Context

Milestone 12 is the first item in `docs/architecture.md`'s `12+` roadmap row
("Dashboard, alerts, labels, load/chaos testing, k8s/Terraform") to actually
be built: an operations console (`dashboard/`, reserved but empty since
ADR-0003 excluded it from the uv workspace, and `DASHBOARD_PORT` reserved in
`.env.example` since before this milestone had a design). Grafana (ADR-0010)
already answers the aggregate question -- "what is the p99 latency, what is
the fallback rate" -- from Prometheus. It structurally cannot answer the
complementary question an operator asks next: "show me this account's recent
transactions and why each was scored the way it was." That answer lives in
Postgres, keyed by business identifiers (account, transaction), not in a time
series.

Two things need deciding before any frontend code is worth writing: where the
dashboard's read data comes from, and whether this milestone introduces the
system's first authentication boundary.

## Decision

**The gateway gains a read endpoint, `GET /v1/transactions`, rather than a
new query service.** The gateway already owns the `fraudguard-db` session and
the `Transaction`/`Decision` models (ADR-0005) -- it is the one place in the
system that already has everything a feed view needs, with no new
inter-service dependency. A separate read-only service would need its own
Dockerfile, compose entry, and database credentials to answer a question the
gateway can already answer with one more route. This does put a second
concern (ops read traffic) on a service ADR-0009 designed around a strict hot-
path latency budget; accepted because `GET /v1/transactions` is a plain,
indexed, paginated Postgres query with no feature-service/model-service calls
in it, so it cannot compete with the hot path for those two dependencies'
capacity, and FastAPI serves both from the same event loop without one
blocking the other.

**One endpoint, not two.** `GET /v1/transactions` returns each transaction
with its decision embedded (nullable -- a transaction can exist without a
persisted decision if the process crashed between the two writes in
`transactions.py`), rather than separate `GET /v1/transactions` and
`GET /v1/decisions` endpoints the dashboard would have to join client-side.
The feed view this milestone needs -- "recent transactions and their
outcomes" -- is one query (`selectinload` on the `decision` relationship, no
N+1), not two.

**Paginated with `limit`/`offset`, ordered by `occurred_at` descending.** The
simplest pagination that answers "what happened most recently" -- the only
access pattern this milestone's feed view needs. Cursor-based pagination is
more correct under concurrent inserts but is unjustified machinery for an
internal ops console with no untrusted caller driving deep pagination.

**No authentication.** The dashboard, like Grafana's already-accepted
anonymous local-dev access (ADR-0010, `docker-compose.yml`), ships with no
auth boundary. Introducing the system's first authentication mechanism is a
separate architectural decision on its own -- session vs. token, where
credentials live, who issues them -- with no forcing function yet (there is
exactly one operator: whoever runs `docker compose up`). Scoping it into this
milestone would block a visibility feature on an unrelated, larger decision.
This is a documented, accepted gap, not an oversight: **`GET /v1/transactions`
must never ship this way past a genuinely multi-tenant or internet-facing
deployment**, the same caveat README already carries for Grafana.

**CORS is scoped to exactly one origin, from settings.** The dashboard's
browser JS calls the gateway from a different origin (`DASHBOARD_PORT` vs.
`GATEWAY_PORT`), which requires the gateway to send CORS headers or every
browser refuses the response. `GatewaySettings.dashboard_origin` (default
`http://localhost:8080`, matching `DASHBOARD_PORT`) is the only allowed
origin, methods restricted to `GET`, no credentials -- the smallest CORS
surface that makes the dashboard work, per CONTRIBUTING's "configuration
comes from the environment" rule, not a wildcard `allow_origins=["*"]`.

## Alternatives considered

- **A new `services/query` (or `services/dashboard-api`) read-only service.**
  Rejected: a second service reading the same Postgres tables the gateway
  already has a session for buys isolation the current single-operator,
  no-auth deployment does not need, at the cost of a new deployable, a new
  ADR-required service boundary (CONTRIBUTING), and a new set of database
  credentials to manage. Revisit if the dashboard's read load ever needs to
  scale independently of the hot path, or once auth makes "who can read
  decisions" a real access-control question distinct from "who can score
  transactions."
- **Two endpoints, `GET /v1/transactions` and `GET /v1/decisions`.**
  Rejected: nothing in this milestone's scope needs decisions independent of
  their transaction, and a client-side join across two paginated endpoints is
  strictly more complex than one query with `selectinload` for no benefit
  this milestone can name.
- **Auth now (a shared API key, or session-based login).** Rejected: no
  threat model yet distinguishes "the operator running docker compose" from
  "the dashboard's browser tab" -- they are the same person on the same
  machine in the only deployment this system has. Adding it here would
  conflate a visibility milestone with an access-control milestone that
  deserves its own ADR once there is a second operator or a non-local
  deployment to protect against.
- **Cursor-based (keyset) pagination.** Rejected: correct under concurrent
  writes in a way `limit`/`offset` is not, but this milestone has no caller
  paging deep enough, or under write concurrency severe enough, for that
  correctness gap to matter yet.
- **Wildcard CORS (`allow_origins=["*"]`).** Rejected: `GET /v1/transactions`
  returns real transaction and decision data; a wildcard origin would let any
  page in any tab read it via the browser's fetch API the moment auth is
  ever removed from the threat model's "not needed yet" column. One
  configured origin costs nothing extra to set correctly.

## Consequences

**Positive**

- The dashboard's data layer needs zero new infrastructure: one route on a
  service that already runs, already has a Postgres session, and is already
  in `docker-compose.yml`'s dependency graph.
- One query, one response shape (`TransactionFeedItem`, transaction fields
  plus an embedded nullable decision) is the entire read contract the
  dashboard depends on.
- The CORS origin being a setting, not a hardcoded value, means a future
  non-default `DASHBOARD_PORT` does not silently break the dashboard.

**Negative, and accepted**

- The gateway is no longer purely a hot-path scoring service -- it now also
  serves ops read traffic. Accepted because the new endpoint is cheap
  (indexed Postgres reads, no feature-service/model-service calls) and does
  not share a resource the hot path is actually constrained on.
- No authentication on data that includes transaction amounts and account
  identifiers. Acceptable only because the current and only deployment target
  is a single operator's local Docker Compose stack; this must be revisited
  before any shared or internet-facing deployment, the same caveat already
  attached to Grafana's anonymous access.
- `limit`/`offset` pagination can skip or repeat rows under concurrent
  inserts at the page boundary. Acceptable for an ops feed a human is
  scrolling, not a system relying on exactly-once delivery of pages.
