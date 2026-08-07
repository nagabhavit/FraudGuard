# ADR-0006: Kafka event publishing

- **Status:** Accepted
- **Date:** 2026-08-07

## Context

Milestone 6 puts the gateway's transaction stream onto Kafka, durably, so
the cold path (stream aggregator, training pipeline — later milestones) has
something to consume. Three things need deciding together:

1. Which Kafka client the gateway uses to produce, given it is an async
   FastAPI service under the same latency discipline as ADR-0005 — a
   blocking client call inside an `async def` handler stalls the event loop
   for every in-flight request, not just the one producing.
2. How messages are Avro-encoded against the Confluent Schema Registry
   already running in `docker-compose.yml` (`SCHEMA_REGISTRY_SCHEMA_COMPATIBILITY_LEVEL: backward`).
3. Where topic names, partition counts, and schemas are declared, given the
   future stream aggregator (Milestone 8) must agree with the gateway on all
   three — `KAFKA_AUTO_CREATE_TOPICS_ENABLE` is `false` specifically so a
   topic's shape is a reviewed decision, not whatever the first producer
   happened to send.

## Decision

**A new workspace member, `libs/fraudguard-events`**, holds topic
declarations, Avro schemas, the Schema Registry client, and the wire-format
codec — the same reasoning as ADR-0005 applied to the event contract instead
of the database schema: one definition, shared by the gateway (producer
today) and the aggregator (consumer, Milestone 8).

**The producer client is `aiokafka`.** It is a pure-Python, `asyncio`-native
client — a produce call is a real `await`, not a thread-pool-wrapped
blocking call, so it composes with the rest of the async request path
without a compatibility shim.

**Avro encoding uses `fastavro` plus a small hand-written Schema Registry
client**, not `confluent-kafka`'s bundled `AvroSerializer`. The Confluent
wire format itself is five bytes of overhead (a magic byte, then a 4-byte
big-endian schema ID) in front of the Avro body — simple enough to implement
directly against `fastavro`, and doing so avoids taking `confluent-kafka`
(a `librdkafka` C-extension) as a dependency purely for its serializer
helpers when the actual Kafka I/O is already handled by `aiokafka`.
Schema registration and lookup go through the Schema Registry's plain REST
API (`httpx2`, already a workspace dependency since ADR on the gateway's
test client), which is a small, stable surface — register-schema and
get-schema-by-id are the only two calls this milestone needs.

**Topics are declared as code in `fraudguard_events.topics`** (name,
partition count, replication factor, retention) and created explicitly by
`ops/scripts/create_kafka_topics.py`, an idempotent script — never by
relying on `KAFKA_AUTO_CREATE_TOPICS_ENABLE`, which is off deliberately (see
`docker-compose.yml`).

**Publishing failures do not fail the request.** Postgres, written first, is
the durable record of a received transaction (ADR-0005); Kafka is the log
that feeds the cold path, not the system of record. If the broker is
unreachable, the gateway logs the failure and still returns success for a
transaction it has durably persisted — the alternative (failing the
request) would make payment authorization depend on Kafka's availability,
which is exactly what "Kafka is not in the request path" (README) rules
out. The accepted gap this leaves — a transaction persisted but never
published — is a known limitation; closing it properly means an outbox
pattern (a row a separate process publishes and marks sent), which is
out of scope until there is a second producer to justify the extra
machinery.

## Alternatives considered

- **`confluent-kafka` for both transport and Avro serialization.** Rejected:
  it is the most complete option and the one most Kafka tutorials assume,
  but it wraps `librdkafka`, a C library, whose wheels are prebuilt for
  common platforms but are still a native dependency the rest of this
  workspace's stack does not otherwise need (`asyncpg` and `aiokafka` are
  both pure Python). `aiokafka` + `fastavro` covers the same ground with
  dependencies that build the same way everywhere `uv sync` already works.
- **`kafka-python` for transport.** Rejected: synchronous by design: every
  produce call would need `run_in_executor`, reintroducing the exact
  thread-pool shim `aiokafka` exists to avoid, for no benefit over using an
  async-native client directly.
- **Fail the request if the Kafka publish fails.** Rejected: makes payment
  authorization availability a function of Kafka's availability, which
  contradicts the architecture's central premise (README: "Kafka is
  deliberately not in the request path").
- **Rely on `KAFKA_AUTO_CREATE_TOPICS_ENABLE` instead of an explicit
  creation script.** Rejected before this ADR, by the original
  `docker-compose.yml` comment: auto-created topics get one partition and
  default retention, silently, and the aggregator would have no reviewed
  contract for partition count or key to depend on.

## Consequences

**Positive**

- No native/C-extension dependency added to the workspace for Kafka.
- Topic shape and schema are reviewed, versioned artifacts
  (`fraudguard_events.topics`, `libs/fraudguard-events/schemas/*.avsc`), not
  inferred from traffic.
- A Kafka outage degrades to "events are not being published," which is
  observable and recoverable, rather than "payments cannot be authorized."

**Negative, and accepted**

- A transaction can be durably persisted in Postgres without ever reaching
  Kafka if the publish fails after the database commit. Documented above;
  revisit with an outbox pattern once a second producer or a stricter
  delivery guarantee is needed.
- Hand-rolling the Confluent wire-format codec is a small piece of protocol
  code this workspace now owns and tests, rather than importing it from
  `confluent-kafka`. The format is stable and unlikely to change, which is
  why this is judged worth it to avoid the native dependency.
