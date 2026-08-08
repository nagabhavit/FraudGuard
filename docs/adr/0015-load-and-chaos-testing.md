# ADR-0015: Load and chaos testing

- **Status:** Accepted
- **Date:** 2026-08-09

## Context

`docs/architecture.md`'s roadmap bundles the remaining work into one
unscoped `15+` row: "Load/chaos testing, k8s/Terraform." Two independent
signals in the repository's own documentation say this milestone should
scope out load and chaos testing specifically, leaving k8s/Terraform for
later:

- `README.md`'s repository layout already reserves `ops/` for
  "prometheus, alertmanager, grafana, **load tests, chaos experiments**,
  scripts" -- separately from `infra/`, reserved for "terraform modules
  and kubernetes manifests." These were always two different milestones,
  not one.
- ADR-0011 built `services/simulator`'s generation (`TransactionFactory`)
  and sending (`driver.py`) as deliberately separate pieces specifically
  "so later load-testing work can drive the same factory harder without
  a second implementation" -- the clearest "already prepared, pick me
  next" signal anywhere in this codebase.

Every earlier milestone made a claim and verified it once, by hand,
against a quiet local stack: the README's p99 <= 100ms hot-path budget,
the degradation ladder falling back correctly under a dependency outage
(ADR-0009), a sustained fallback rate or a downed service actually firing
an alert (ADR-0013, verified once by manually stopping `model-service`).
This milestone turns those one-off manual checks into repeatable tools --
sustained concurrent traffic with real latency percentiles, and
deliberate, scripted dependency outages -- without claiming production
load-testing or chaos-engineering maturity a portfolio project's single
local Compose stack cannot back up.

Four things need deciding before any code is worth writing: where
load-testing logic lives, whether chaos experiments are scripted tools or
a runbook, whether either runs in CI, and which dependencies get a chaos
experiment this milestone.

## Decision

The following four points were explicitly reviewed and approved before any
implementation code was written, and must not be silently changed during
implementation:

1. A duration-based stop condition for the load driver (not a fixed count).
2. `asyncio.Semaphore` / a bounded worker-pool for concurrency.
3. The load driver lives at `services/simulator/src/simulator/load.py`,
   exposed via `python -m simulator.load`.
4. Chaos verification uses the gateway's actual response and
   `GET /v1/transactions` (`model_version`) as the self-verifying
   application signal for model-service and feature-service, not
   Alertmanager's alert-firing state -- with Kafka's per-target
   application, revised after real-stack verification found the
   originally intended signal does not work, spelled out in "Acceptance
   criteria" and "Verification findings" below.

**Load testing extends `services/simulator`, not a new external tool.**
A new module, `simulator/load.py`, adds a bounded-concurrency driver
(`asyncio.Semaphore`-gated workers) that reuses the existing
`TransactionFactory` and `send_transaction` (`driver.py`), runs for a
fixed wall-clock duration (not a fixed count -- a sustained-load tool
answers "how does the system behave over N seconds under load," which a
fixed count answers only incidentally), and records each request's
latency to report p50/p95/p99 at the end. A new CLI entry point,
`python -m simulator.load`, sits alongside the existing
`python -m simulator` rather than adding flags to it -- the existing tool
proves structural correctness sequentially by design (`driver.run()`'s
own docstring: "concurrency is exactly the dimension Milestone 12+'s
load-testing work would add ... not this function's job"); load testing
is a different tool with a different job, not a mode of the same one.
This follows ADR-0011's explicit design intent and adds no new
dependency, language, or framework to the workspace. These three points
(duration-based stop condition, `asyncio.Semaphore`-bounded concurrency,
this file/CLI location) are approved as specified; implementation must
not deviate from them.

**The percentiles this tool reports are client-observed HTTP latency --
factory-to-response, including network and JSON serialization -- not
`fraudguard_gateway_scoring_duration_seconds`** (ADR-0010's histogram of
the gateway's own feature-service+model-service scoring time alone). The
two measure different things and will not match; the documented
procedure below reports both, so a discrepancy is legible rather than
mistaken for one number lying.

**Chaos experiments are scripted tools under `ops/chaos/`, not a written
runbook.** A parameterized script (`docker compose stop <target>` -> send
traffic via the simulator -> assert the degradation ladder's real signal
via the gateway's own response and `GET /v1/transactions`
(`model_version` null, ADR-0005) -> `docker compose stop` reverted with
`docker compose start <target>` -> assert recovery) is repeatable and
self-verifying, consistent with the "verified against the real stack"
paragraph every ADR since 0009 has closed with. A runbook would document
the same steps but requires a human to run and judge each one by hand
every time, the exact gap scripting closes. This signal is approved as
the chaos-verification mechanism for model-service and feature-service;
see "Acceptance criteria" and "Verification findings" below for Kafka,
where the originally intended analogous signal (ADR-0008's
`GET /health/ready`) was verified against the real stack and found not
to detect a live broker outage -- the signal actually used there is a
pre-existing Prometheus counter instead, still not Alertmanager's own
alert-firing state, which this decision was actually protecting against.

**Milestone 15's chaos targets are `model-service`, `feature-service`,
and Kafka (the aggregator's crash-and-recover path) -- not Redis.**
`model-service` and `feature-service` each independently exercise the
degradation ladder (ADR-0009) from a different trigger point (the two
dependencies the gateway calls in the hot path); Kafka exercises the
aggregator's crash-loop-until-the-dependency-recovers behavior
(ADR-0008) -- the exact mechanism the two most recent CI fixes
(14487ea, ffaabae) just repaired, making it the most apt thing in the
system to now verify on purpose rather than by accident. Redis is
feature-service's own dependency, not an independently documented rung
of the ladder the way a downed model-service or feature-service is;
adding it as a fourth experiment this milestone would cost more than it
proves. Every service's `restart: unless-stopped` (`docker-compose.yml`)
does not fight this: it restarts a container that *crashes*, not one
`docker compose stop` explicitly stopped, so a chaos script's stop/start
cycle is a clean, controlled signal rather than a race against Docker's
own restart policy.

**Neither tool runs in CI.** Both are documented, executed-by-hand
procedures against the local stack, per `CONTRIBUTING.md`'s definition
of done ("the documented test procedure in the milestone description has
been executed and the results match" -- not "automated in CI").
Alertmanager's own rules (ADR-0013) have `for:` durations of 1 to 5
minutes; waiting for a real alert to transition `pending -> firing`
inside CI would burn a large fraction of the `integration` job's already
fairly full 15-minute budget per experiment, and a sustained load run has
no natural place in a fast feedback loop either. This is the same
posture ADR-0013 already accepted for its own thresholds: illustrative
and locally verified, not continuously enforced, because there is no
real incident history or production traffic to calibrate an automated
gate against.

## Acceptance criteria

No traffic rate, concurrency level, duration, or recovery-time number is
asserted here -- per instruction, none of those are invented. Where a
value is needed to actually run a tool, it is supplied by the documented
procedure at execution time (an operator-chosen CLI flag), not mandated
by this ADR. What follows is criteria the tools themselves must satisfy,
testable independent of whatever load level an operator later chooses.

### Load testing

1. `python -m simulator.load` accepts an operator-supplied
   `--duration-seconds` and `--concurrency` and sends
   `TransactionFactory`-generated transactions against a running gateway
   for that duration, bounded to that concurrency. This ADR does not
   assert a specific default as "the" official test run.
2. Every request is classified success or failure (matching the existing
   `RunSummary` convention in `driver.py`); the run itself completes
   without an unhandled exception escaping it, independent of individual
   request outcomes.
3. The tool computes and reports p50, p95, and p99 of the observed
   per-request latency from the run's actual recorded values.
   Correctness of this computation is unit-testable hermetically -- a
   synthetic list of latencies checked against a known-correct reference
   percentile calculation, requiring no live stack.
4. The documented procedure (to be added to `docs/architecture.md`) runs
   this tool against the real Compose stack and records the actual
   observed p50/p95/p99 next to the README's existing, already-documented
   p99 <= 100ms hot-path budget. This milestone's claim is that the tool
   correctly measures and reports latency so that comparison is possible
   -- not that any particular concurrency or duration keeps the system
   under that budget; whether it does is what running the procedure
   reveals, not something this ADR predicts in advance.

### Chaos testing

Each experiment is a script that exits non-zero if any assertion below
fails -- self-verifying, per the "scripted, not runbook" decision above.

1. **Baseline.** Before the target is stopped, a transaction posted to
   the gateway returns `model_version` populated (the real model scored
   it, ADR-0009) for the `model-service` and `feature-service`
   experiments.
2. **Outage signal -- model-service / feature-service.** With the target
   stopped (`docker compose stop <target>`), `POST /v1/transactions`
   still returns 200 -- never hangs, never fails the request (ADR-0009)
   -- and the response, confirmed via `GET /v1/transactions`, has
   `model_version` null: the existing, already-documented fallback
   signal (ADR-0005, ADR-0009), not a new one invented for this
   milestone.
3. **Outage signal -- Kafka.** Kafka's fault domain does not touch the
   gateway's response at all (ADR-0006: the publish is best-effort and
   never affects hot-path scoring), so `model_version` cannot be the
   signal here. The originally intended signal, the aggregator's own
   `GET /health/ready` / `checks.kafka_consumer`, was verified against
   the real stack and found not to detect this fault -- see
   "Verification findings" below for the full account. The signal
   actually used is `fraudguard_gateway_kafka_publish_total{outcome=
   "failure"}` (ADR-0013, a pre-existing metric), confirmed by direct
   measurement to increment during a real outage. `checks.kafka_consumer`
   is still checked and asserted `"ok"` on every experiment run, as the
   documented limitation -- verified and recorded each time, not
   silently dropped once it stopped being the pass/fail signal.
4. **Recovery.** After `docker compose start <target>`, the script polls
   (its own internal loop, not a fixed sleep, and not a documented
   recovery-time SLA this project claims) until the relevant signal
   returns to its baseline state: `model_version` populated again for
   model-service/feature-service; for Kafka,
   `fraudguard_gateway_kafka_publish_total{outcome="success"}`
   incrementing again on a fresh transaction, alongside that transaction
   itself completing quickly again (`checks.kafka_consumer` never left
   `"ok"` in the first place, per the finding above, so it has nothing to
   recover back to). Confirming recovery this way, rather than against
   an invented time bound, matches this project's existing pattern of
   polling until a condition holds (`test_end_to_end_integration.py`'s
   hot-and-cold-path test already does this for feature-service
   velocity, ADR-0011).

## Verification findings

Verified against the real stack (`docker compose stop kafka` /
`docker compose start kafka`), the Kafka experiment's originally intended
signal does not detect the fault it was chosen to detect. Recorded here
because it changed what the Kafka experiment actually checks (Acceptance
criteria above) -- not fixed in application code, per explicit direction.

**`checks.kafka_consumer` never leaves `"ok"` during a live Kafka broker
outage.** Polled every 5 seconds for 40+ seconds while Kafka was
stopped, `GET /health/ready` on the aggregator reported
`{"status":"ok","checks":{"redis":"ok","kafka_consumer":"ok"}}`
throughout -- unchanged. The aggregator's own logs show why: `aiokafka`
retries a lost broker connection internally ("Unable connect to node
with id 1: [Errno 111] Connection refused", "Marking the coordinator
dead (node 1) for group fraudguard-aggregator") without the `async for
message in self._consumer:` loop in `Aggregator.run_forever()`
(`services/aggregator/src/aggregator/consumer.py`) ever raising or
exiting, so `self.running` never flips to `False`. ADR-0008's documented
behavior ("the consume task exiting... must be a health signal") covers
the *startup-time* case this project already fixed in CI (a missing
topic -- commits 14487ea/ffaabae) -- not a broker outage after the
consumer is already running, a distinct fault mode ADR-0008 did not
anticipate.

**This is accepted as a known, documented observability limitation, not
fixed here.** Per explicit direction: `aggregator/health.py`,
`consumer.py`, and ADR-0008 are unchanged by this finding. Fixing the
aggregator's own readiness check is a defensible follow-up, but a
different, larger change (application code and an already-accepted ADR)
than this milestone's scope of *testing* the system that exists, not
modifying it. `ops/chaos/experiment.py`'s Kafka experiment explicitly
checks and prints that `checks.kafka_consumer` stays `"ok"` during the
outage on every run -- the limitation is verified and recorded each
time, not silently removed from the script once it stopped being a
usable pass/fail signal.

**The reliable application-level signal turned out to be the gateway's
own `fraudguard_gateway_kafka_publish_total{outcome}`** (ADR-0013,
already existed before this milestone) -- confirmed by direct
measurement: with Kafka stopped, one `POST /v1/transactions` took
**43.1 seconds** to return (still HTTP 200, still a real model score --
the delay is entirely the gateway's own best-effort publish attempt
blocking the response before it returns, the same "Known gap" already
documented in `docs/architecture.md`'s Kafka topics section, here shown
to be more severe for a fully unreachable broker than the previously
observed missing-topic case), and
`fraudguard_gateway_kafka_publish_total{outcome="failure"}` incremented
by exactly one. After restarting Kafka, a fresh transaction completed in
**0.76 seconds** and `{outcome="success"}` incremented immediately.
`ops/chaos/experiment.py` gives its Kafka-target gateway client a 90s
timeout specifically to outlast the measured 43.1s delay, rather than
timing out client-side before the gateway's own attempt gives up.

**This revises decision point 4's "not Prometheus or Alertmanager"
framing, specifically and only for Kafka.** That constraint, approved
before any live-stack verification, meant "don't gate this milestone's
pass/fail on Alertmanager's own alert-firing state" -- the CI-timing
argument elsewhere in this ADR. It did not anticipate that the *only*
reliable non-Alertmanager application signal for this specific fault
would itself be a Prometheus counter rather than a plain HTTP-response
field. Using `fraudguard_gateway_kafka_publish_total` here is still "a
real application signal, not Alertmanager's alert-firing state" in
spirit -- applied to the one target where the originally assumed
HTTP-response-shaped signal does not work. model-service and
feature-service are unaffected and still use exactly the originally
approved gateway-response / `GET /v1/transactions` signal.

## Alternatives considered

- **An external load-testing tool (k6 or Locust).** Rejected: k6 is a
  separate Go/JS tool and Locust is a new Python framework, both adding
  a dependency this workspace does not otherwise need, and both would
  duplicate the realistic-payload generation `TransactionFactory`
  already does -- the same reasoning ADR-0011 used against `numpy` for
  the factory itself.
- **A fixed request count instead of a duration for the load driver.**
  Rejected as the primary mode: a count-based run's wall-clock length
  depends on how fast the system responds, which is backwards for a tool
  meant to answer "what does sustained load over a known window do to
  latency." (A count is still useful for quick smoke runs; the CLI can
  offer both, with duration as the default.)
- **A written runbook for chaos experiments, no new code.** Rejected:
  less code to maintain, but not repeatable without a human running and
  judging every step, which is the exact gap ADR-0013's one manual
  verification already showed the cost of -- it happened once, by hand,
  and was never repeated since.
- **Wiring load and/or chaos into `.github/workflows/ci.yml`, a new or
  extended job.** Rejected for now: Alertmanager's `for:` windows alone
  would consume minutes per experiment against a budget the `integration`
  job does not have to spare, and a sustained load run has no natural
  fit in a fast feedback loop. Revisit if this project ever needs a
  scheduled (not per-push) performance/chaos job, which is a different
  shape of CI entirely.
- **Including Redis as a fourth chaos target this milestone.** Rejected
  as more than the smallest correct scope: Redis failure is
  feature-service's own dependency to handle, not an independently
  documented degradation-ladder rung the way model-service/feature-service
  down are. Revisit alongside a feature-service-focused milestone if one
  is ever scoped.

## Consequences

**Positive**

- The README's p99 <= 100ms claim and the degradation ladder's ADR-0009
  behavior move from "verified once, by hand, at low traffic" to
  "reproducible with a documented command," the same maturation every
  earlier milestone's tooling already went through.
- No new dependency, language, or deployed service: both tools are
  host-side Python, reusing what `services/simulator` already provides,
  consistent with this workspace's consistent aversion to unnecessary
  weight (ADR-0003, ADR-0006, ADR-0011).
- Kafka's chaos experiment specifically exercises the aggregator
  startup/recovery path two separate CI fixes just spent effort
  repairing -- this milestone is also a regression check on that fix,
  not just new coverage.

**Negative, and accepted**

- Neither tool runs in CI, so a future regression in the degradation
  ladder or the hot-path budget is caught only when someone remembers to
  run these tools by hand. Accepted for the reasons above; revisit if a
  scheduled (not per-push) CI job is ever justified.
- The load driver's reported percentiles are client-observed, not the
  gateway's own scoring-duration metric -- a discrepancy between the two
  is expected and must be read correctly, not treated as one of them
  being wrong. Documented above and in the procedure itself specifically
  so this is not a future source of confusion.
- Chaos coverage this milestone is deliberately partial (three targets,
  not every dependency). Documented as scope, not an oversight; Redis is
  the named candidate for a later pass.
- The Kafka experiment's originally intended signal (`checks.kafka_consumer`)
  does not actually detect a live broker outage -- see "Verification
  findings" above. Accepted as a known observability limitation
  (`aggregator/health.py` and ADR-0008 unchanged); the experiment now
  verifies outage/recovery via `fraudguard_gateway_kafka_publish_total`
  instead, and still checks and records the limitation on every run
  rather than removing all trace of it.
