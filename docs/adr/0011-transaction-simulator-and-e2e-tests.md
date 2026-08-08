# ADR-0011: Transaction simulator and real-stack end-to-end tests

- **Status:** Accepted
- **Date:** 2026-08-08

## Context

Milestone 11 is the one item on the roadmap with no prior decision to lean
on: `docs/architecture.md` describes it in a single roadmap-table line
("Transaction generator, end-to-end tests against the real Compose stack")
and nothing else. Every earlier milestone's integration tests
(`services/*/tests/*_integration.py`) build their own service's app
*in-process* via `create_app()` and only reach out to real infrastructure
(Postgres, Kafka, Redis, Schema Registry) -- none of them make an HTTP call
to another service's actual *container*. The closest existing thing,
`test_full_pipeline_integration.py`, chains gateway's and feature-service's
apps together in one test process through real Kafka and Redis, but the
gateway "the test talks to" there is still Python objects in the test's own
memory, not the `fraudguard-gateway` container `docker compose up` starts.
That gap -- proving the actual deployed containers talk to each other
correctly, not just that each service's code is individually correct against
real infra -- is what has, until now, only ever been checked by hand (`curl`,
extensively, throughout Milestones 9 and 10). This milestone closes it, and
needs a realistic traffic source to do it with, since a trivial
all-identical-payload generator would only ever exercise `approve` and prove
nothing about the decision spectrum.

## Decision

**A new workspace member, `services/simulator`, not an `ops/scripts/`-style
bare script.** Every other component in this repository gets an ADR, a
`src/` layout, hermetic tests, `pytest.mark.integration` tests where
relevant, and `mypy --strict` coverage; `ops/scripts/create_kafka_topics.py`
is the one precedent for a bare script, and it is deliberately trivial
(create-if-missing, no business logic worth testing). The transaction
generator is not trivial -- it needs a believable mix of account behavior to
be useful at all -- and `testpaths = ["services", "libs"]` in the root
`pyproject.toml` excludes `ops/` from pytest entirely, which would leave the
one new piece of logic in the milestone about testing with zero tests of its
own. `services/simulator` gets none of the things that make the four real
services deployable (**no `Dockerfile`, no `docker-compose.yml` service
entry**) -- it is a client that runs *against* the compose stack from the
host, never a member of it.

**The generator and the driver are separate, composable pieces.**
`simulator.factory.TransactionFactory` produces one valid
`TransactionCreate`-shaped payload per call from a seeded RNG, with no
knowledge of HTTP, rate, or how many; `simulator.driver` takes a factory, an
`httpx2.AsyncClient`, and a count/rate, and is the only piece that knows how
to send things. This split exists specifically so Milestone 12+'s
load-testing work can import `TransactionFactory` and drive it far harder
through a different, throughput-oriented driver, instead of writing a second
transaction-generation implementation that quietly drifts from this one.

**The factory reuses `ml/pipelines/train.py`'s account-archetype idea, not
its code.** A fixed pool of accounts is split 90% "normal" / 10% "bursty" at
factory-construction time (seeded, so a run is reproducible); bursty
accounts get higher-velocity, higher-amount transactions. `train.py`
generates feature vectors directly for training; the factory generates raw
`TransactionCreate` fields (`account_id`, `merchant_id`, `amount`,
`currency`, `occurred_at`) that flow through the real gateway, so the
underlying velocity/amount signal only emerges after the real hot and cold
paths process it -- the two are conceptually the same idea applied to two
different layers, not shared code. `occurred_at` is always close to
wall-clock "now" (not a fixed timestamp), the same requirement
`test_full_pipeline_integration.py` and the README's own curl example
already document, since a stale timestamp falls outside the 1-minute
velocity window `feature-service` reads. No `numpy` dependency: Python's
stdlib `random` (`lognormvariate` for amounts, `gauss`/`randint` for
velocity-like counts, weighted `choices` for archetype selection) is enough
for believable-shaped test traffic, and pulling in `fraudguard-ml` or
`numpy` for a CLI tool that does no modeling would be exactly the kind of
unnecessary weight ADR-0003 and ADR-0009 both already avoided elsewhere
(the gateway image never carries LightGBM; this tool doesn't need to either).

**The black-box tests assert structural correctness, not exact outcomes.**
CI trains a fresh model every run (`ml/pipelines/train.py`, wired into the
`integration` job in Milestone 9); asserting "this exact payload always
declines" would couple the test suite to that run's specific random
training data and manufacture flakiness. Tests instead assert *shape*:
`outcome` is a valid `DecisionOutcome`, `risk_score` is in `[0, 1]`,
`model_version` starts with `"fraud-lgbm-"` when non-null, `reason_codes` is
a non-empty list exactly when `model_version` is non-null -- the same kind
of assertion `services/model-service/tests/test_scoring_integration.py`
already makes against the one real trained model today. Two tests, not one:
a **hot-path test** posts a batch of factory-generated transactions straight
to the real gateway container and checks each response's shape; a
**hot-and-cold-path test** posts several transactions for one specific
account, then polls the real feature-service container's
`GET /v1/features/{account_id}` and asserts the velocity counts reflect
them -- the same proof `test_full_pipeline_integration.py` already makes
in-process, now made against the actual deployed containers instead.

**CI runs these in the existing `integration` job, which must start more
containers than it does today.** `.github/workflows/ci.yml`'s `integration`
job currently runs `docker compose up -d --wait --build postgres redis
kafka schema-registry feature-service model-service` -- notably missing
`gateway` and `aggregator`, because nothing before this milestone needed
them running as containers rather than as in-process `TestClient` apps. That
list grows to include both. A new CI job was considered and rejected: the
`integration` job already has the right `docker compose up --wait` +
Kafka-topic-creation sequence, and Milestones 9 and 10 both extended it the
same way rather than forking a new one.

## Alternatives considered

- **A bare `ops/scripts/`-style script**, matching `create_kafka_topics.py`.
  Rejected: `ops/` is excluded from `testpaths`, so the one piece of
  meaningfully-complex new logic in this milestone would ship with no
  automated tests at all, on the milestone that is literally about testing.
- **A new top-level category (e.g. `tools/simulator`)** instead of
  `services/simulator`, to avoid implying it's a deployable service.
  Rejected: `services/*` already means "a uv workspace member with its own
  `pyproject.toml`, tests, and strict typing" as much as it means
  "deployable" in practice, and inventing a new, undocumented top-level
  repository category for one component costs more (a new thing every future
  contributor has to learn) than the minor inaccuracy of the name costs.
  The absence of a `Dockerfile`/compose entry makes the distinction obvious
  to anyone who looks.
- **One monolithic script combining generation and sending**, the simplest
  thing that would satisfy this milestone alone. Rejected in favor of the
  factory/driver split specifically so Milestone 12+ does not have to choose
  between reimplementing realistic transaction generation or clumsily
  importing internals out of a script never designed to be imported.
- **Asserting exact decision outcomes** for specific crafted payloads (e.g.
  "amount=10000 always declines"). Rejected: couples tests to one CI run's
  randomly-trained model instead of the contract the gateway actually
  promises (a valid decision, made inline, with real latency) -- the thing
  this milestone is supposed to prove.
- **Only the hot-path test, no cold-path check via feature-service.**
  Considered as the simpler option, since it needs fewer containers running
  in CI. Rejected: it would leave this milestone's "against the real Compose
  stack" claim proving less than `test_full_pipeline_integration.py` already
  proves in-process, which would be a regression in confidence dressed up as
  a new milestone.
- **A new, separate CI job for these tests.** Rejected: no benefit over
  extending `integration`, which already provisions everything needed except
  two more `docker compose up` service names; a second job would duplicate
  the model-training and topic-creation setup steps for no reason.

## Consequences

**Positive**

- The actual deployed containers' HTTP surface is now covered by automated
  tests, not just each service's own code against real infra in isolation --
  closing the gap every prior milestone's integration tests left open by
  construction.
- `TransactionFactory` is a clean, reusable seam for Milestone 12+'s
  load-testing work, decided now while the shape of "one realistic
  transaction" is fresh, rather than reverse-engineered from a script later.
- Structural (not exact-outcome) assertions mean this suite stays stable
  across model retrains, including the fresh-model-per-CI-run setup already
  in place since Milestone 9.

**Negative, and accepted**

- `services/simulator` is a `services/*` member that is neither
  containerized nor deployed, a real (if flagged and justified) departure
  from what that directory has meant so far. Anyone skimming
  `docker-compose.yml` for "every service" will not find it there, by
  design, and the README's repository-layout description needs to say so
  explicitly rather than leaving it as a silent exception.
- The `integration` CI job grows heavier (two more containers to start and
  wait healthy) and slightly slower. Accepted: still one job, still well
  under its 15-minute timeout budget based on Milestones 9/10's experience,
  and the alternative (a thinner but weaker test) was rejected above for a
  specific reason, not by default.
- Structural assertions catch less than exact-outcome assertions would in
  the specific case of a model that has silently regressed to always
  predicting the same class. Accepted: `model-service`'s own test suite
  (`test_scoring_integration.py`) already checks that a bursty/high-amount
  transaction scores meaningfully higher than a quiet one against the real
  trained model -- that is the right layer for a model-quality regression
  check, not this milestone's black-box container test.
