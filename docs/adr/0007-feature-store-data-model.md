# ADR-0007: Feature store data model

- **Status:** Accepted
- **Date:** 2026-08-07

## Context

Milestone 7 makes Redis load-bearing for the first time -- until now it was
declared infrastructure (`docker-compose.yml`, `noeviction` policy already
justified in `.env.example` in anticipation of this) with nothing reading or
writing it. The README's central architectural move is precomputing
features asynchronously and serving them from memory synchronously; this
milestone builds the store those features live in and the service that
serves them, for two concrete fraud signals: transaction *velocity* (how
many transactions has this account made recently?) and merchant
*diversity* (how many distinct merchants recently?).

Three things need deciding: the Redis client, the data structure each
signal is stored in, and how far this milestone reaches into the hot path.

## Decision

**The Redis client is `redis.asyncio`** (the official `redis` package).
Async-native like `asyncpg` and `aiokafka` already are, and -- unlike the
Kafka client decision in ADR-0006 -- there is no native-dependency
trade-off to weigh: `redis-py`'s async client has no required C extension.

**Velocity is a per-account sorted set**, not a fixed counter. Key
`velocity:{account_id}`, member the transaction's `event_id`, score its
`occurred_at` as epoch seconds. Reading a window is `ZCOUNT` between
`now - window` and `now`; the same set answers 1-minute, 1-hour, and
24-hour windows without maintaining a separate key per window. Every write
trims entries older than the longest tracked window
(`ZREMRANGEBYSCORE`) and refreshes a TTL slightly longer than that window,
so an account that goes quiet does not hold a key forever.

**Merchant diversity is a HyperLogLog per account per calendar day**, not
one long-lived HLL per account. Key `merchant_hll:{account_id}:{date}`,
`PFADD` per transaction, TTL'd for two days. Reading unions the last two
day-buckets with `PFCOUNT key1 key2` -- Redis computes the union at read
time without merging state into a third key. Bucketing by calendar day
rather than a precise rolling window means a read near midnight is fuzzy by
up to a few hours; accepted in exchange for O(1) buckets per query and
automatic expiry with no maintenance job.

**A new service, `feature-service`, exposes the read side over HTTP**
(`GET /v1/features/{account_id}`). The write side
(`FeatureStore.record_transaction`) and read side live in one shared
library, `fraudguard-features`, so the future stream aggregator
(Milestone 8) writes through the exact schema this milestone's read API
already relies on, rather than two independent implementations that can
drift. An account with no history returns a feature vector of zeros, not
404 -- "no transactions yet" is the normal state for a new account, not an
error.

**The gateway is not wired to call `feature-service` in this milestone.**
Nothing on the other end needs a feature vector yet -- the model service
that would consume one is Milestone 9. Wiring the call now would be a
request path with nothing to decide with the response, and Milestone 7's
own scope (per `docs/architecture.md`) is the store and its read API, not
the hot-path integration.

## Alternatives considered

- **`INCR`-based fixed counters with `EXPIRE`, one key per window
  (`velocity:{account_id}:1m`, `:1h`, `:24h`).** Rejected: a fixed counter
  is a step function -- it resets abruptly at expiry rather than sliding --
  and three independent counters per account can drift out of sync with
  each other and with the underlying event stream. One sorted set, read
  with different window arguments, cannot drift from itself.
- **A single, never-expiring HLL per account for lifetime merchant
  cardinality.** Rejected: the fraud signal is in *recent* diversity: a
  lifetime count answers a different question ("has this account ever used
  many merchants") than the one that matters here ("is this account
  suddenly using many merchants right now"), and cannot be windowed after
  the fact without rebuilding from raw events.
- **`PFMERGE` into a running merged key on every write, instead of
  `PFCOUNT` across day-buckets at read time.** Rejected: `PFCOUNT` already
  unions multiple keys non-destructively; `PFMERGE` would only earn its
  keep if something needed a single persistent merged artifact, which
  nothing here does.
- **Wire the gateway to call `feature-service` now, ahead of the model
  service.** Rejected: nothing would consume the response yet, so the only
  effect would be added hot-path latency and a new failure mode with no
  corresponding benefit. Deferred to Milestone 9, alongside the model
  service that actually needs it.

## Consequences

**Positive**

- Both signals share the "trim/TTL on write, aggregate on read" shape,
  so the pattern for adding a third signal later is already established.
- The write and read APIs living in one library means Milestone 8's
  aggregator cannot silently disagree with `feature-service` about key
  naming or windowing.
- No native dependency added for the Redis client, consistent with the
  rest of the workspace's driver choices where a pure option exists.

**Negative, and accepted**

- Day-bucketed HLL diversity is approximate near a bucket boundary, not a
  precise rolling 24 hours. Acceptable for a fraud *signal* (a strong prior,
  not a ledger entry); revisit if a future consumer needs exactness.
- Until Milestone 8 builds the real consumer, `record_transaction` has no
  live caller -- this milestone's tests exercise it directly against real
  Redis rather than via a Kafka consumer that does not exist yet.
