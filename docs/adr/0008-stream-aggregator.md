# ADR-0008: Stream aggregator design

- **Status:** Accepted
- **Date:** 2026-08-07

## Context

Milestone 8 closes the loop the earlier milestones left open: the gateway
publishes `TransactionReceived` events (Milestone 6) and `fraudguard-features`
defines how they should be folded into Redis (Milestone 7,
`FeatureStore.record_transaction`), but nothing has been consuming the topic
and calling that method. This milestone builds that consumer -- a
long-running worker, not a request/response API, which raises three
questions the earlier services didn't: how offsets are committed, how a
message that fails to process is handled, and what "ready" means for a
process with no inbound requests.

## Decision

**Offsets are committed manually, after processing, once per message --
always, even on failure.** `enable_auto_commit=False`; the consumer calls
`commit()` in a `finally` block around each message's processing. This is
safe *because* `FeatureStore.record_transaction` is idempotent: replaying
the same event twice (`ZADD` the same member/score, `PFADD` the same value)
produces the same state as processing it once, so an at-least-once restart
after a crash cannot corrupt a feature. A message that fails to decode or
apply is logged with its offset and skipped, not retried indefinitely --
see the poison-message discussion below.

**Schema resolution is a per-process, in-memory cache keyed by schema ID.**
Every message's first five bytes carry a magic byte and a 4-byte schema ID
(ADR-0006's wire format); the consumer looks up the ID once, from the
Schema Registry, and reuses the schema for every later message stamped with
the same ID rather than making one HTTP round trip per message.

**A poison message is logged and skipped, not retried and not routed to a
dead-letter topic.** A message this consumer cannot process is either a
transient bug in this consumer (redeploying with a fix reprocesses nothing,
since the bad message is already past) or a schema mismatch that
BACKWARD-compatibility enforcement at the registry should have already
prevented from existing. Retrying it forever would block every message
behind it on the same partition; a dead-letter topic is the correct fix at
production scale but is more machinery than one consumer, with no second
consumer yet to justify it, needs today.

**Readiness reports two things, not one: Redis reachability (`FeatureStore.ping`)
and whether the background consume loop is still running.** A worker with no
inbound requests has no natural request to fail when something is wrong, so
its own consume task exiting (an unhandled exception escaping the loop)
must be a health signal, not a silent hang. The health server and the
consume loop run as two tasks in one process -- a FastAPI app for
`/health/live` and `/health/ready`, and an `asyncio` task running the
consumer -- rather than two separate processes, so a container orchestrator
gets the same liveness/readiness contract every other service in this
repository already exposes.

## Alternatives considered

- **Auto-commit (`enable_auto_commit=True`).** Rejected: auto-commit fires on
  a timer, independent of whether the message was actually applied to
  Redis. A crash between an auto-commit and a completed write loses that
  event silently; committing manually after (attempted) processing ties the
  offset to work actually done.
- **Deduplicate by `event_id` before writing (e.g., a Redis `SETNX` guard).**
  Rejected: unnecessary complexity. `record_transaction`'s own operations
  are already idempotent per event; a second dedup layer would only protect
  against a class of bug (double-processing) that doing nothing already
  protects against.
- **A dead-letter topic for poison messages.** Rejected for now: real value
  once there is a second consumer or an operator workflow to drain it, but
  pure overhead with one. Revisit if `record_transaction` failures turn out
  to be common rather than exceptional.
- **No health server -- a bare worker process, liveness inferred from
  "the container is running".** Rejected: "running" and "correctly consuming"
  are different states (a crashed-but-not-exited consume task, a Redis
  outage) and collapsing them removes exactly the signal an orchestrator
  needs to decide whether to restart the container.

## Consequences

**Positive**

- A consumer crash-restart replays at most the in-flight message, never
  silently loses one, and never corrupts Redis state by replaying it.
- The schema cache means steady-state throughput does one Schema Registry
  round trip per distinct schema version, not per message.
- `/health/ready` distinguishes "Redis is down" from "the consume loop
  died" from "everything is fine" -- three states an orchestrator can act on
  differently, instead of one opaque "unhealthy".

**Negative, and accepted**

- A message that cannot be processed is dropped after being logged, not
  preserved anywhere replayable. Acceptable because BACKWARD compatibility
  at the registry should make this rare, and because Kafka's own retention
  still lets a human replay the raw topic from an earlier offset if a bug
  in this consumer, not the data, turns out to be the cause.
- Single consumer instance, one process. The `fraudguard-aggregator` group
  ID is chosen so a second instance could join the same group and split
  partitions later, but scaling that out is not built or tested here.
- `AIOKafkaConsumer.start()` raises if its topic does not exist yet, which
  fails this service's whole startup -- observed directly when
  `docker compose down`/`up` reset the local Kafka volume and the topic had
  not been recreated yet (`ops/scripts/create_kafka_topics.py`). No retry
  loop is added for this: `restart: unless-stopped` (`docker-compose.yml`)
  already retries the container until the topic exists, which is simpler
  than hand-rolling the same behavior in the consumer for a dependency that
  is either present at real deploy time or a one-line operational fix away
  locally.
