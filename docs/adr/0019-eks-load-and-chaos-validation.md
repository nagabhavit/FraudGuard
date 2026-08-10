# ADR-0019: Load and chaos validation against the real EKS deployment

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

Milestone 15 (ADR-0015) built two tools against the local Docker Compose
stack: `services/simulator/src/simulator/load.py` (sustained concurrent
load, reporting p50/p95/p99 client-observed latency) and
`ops/chaos/experiment.py` (scripted, self-verifying outage/recovery
experiments for `model-service`, `feature-service`, and `kafka`). Both
were designed with non-`localhost` targets already in mind --
`load.py --base-url` and `experiment.py --gateway-url`/`--aggregator-url`
are plain, already-overridable CLI arguments.

Milestone 30 was scoped, per prior planning, to extend this validation to
the real EKS deployment Milestones 16-29 have been building toward,
verifying five claims: latency, fallback behavior, Kafka degradation,
service availability, and resource/autoscaling behavior. The working
assumption going in was that this needs "no code changes, just a
documented procedure."

That assumption held for `load.py`, but not for `experiment.py` --
investigated directly against the actual code, not assumed. Every one of
`experiment.py`'s outage-injection and recovery code paths (all three
targets) calls a single helper, `_docker_compose()`, which shells out to
`docker compose stop <target>` / `docker compose start <target>`. There is
no Kubernetes-native equivalent anywhere in the script. Against a real
EKS deployment, "stop the local Compose container named `model-service`"
is not a meaningful operation -- there is no local Compose stack to stop.

## Decision

**Split the two tools' EKS extension apart, per their actual portability,
rather than treating "extend M30 to EKS" as one uniform task:**

**`simulator/load.py` is extended to the real EKS deployment. No code
changes** -- `docs/runbooks/eks-load-and-chaos-validation.md` documents
running it with `--base-url` pointed at the real Ingress (Milestone 21)
once one is real. This validates three of the five claims: **latency**
(client-observed p50/p95/p99 against the README's hot-path budget),
**service availability** (sustained load against real, possibly-scaling
pods), and **resource/autoscaling behavior** (Milestone 22's HPA
manifests, whose CPU/memory values were explicitly marked illustrative
pending real-load validation -- this is that validation, once it can
actually run).

**`ops/chaos/experiment.py` is NOT extended to EKS this milestone.**
Building a Kubernetes-native outage-injection mechanism (e.g.
`kubectl scale --replicas=0`/`1`, or deleting pods and waiting for
replacements) is real, new capability -- a different-shaped piece of work
than "point an existing tool at a new URL," and a genuine architecture
choice (which mechanism, how "recovered" is detected, what RBAC a
runner needs) this milestone was never scoped to make. The two claims
this would have covered -- **fallback behavior** (the degradation
ladder) and **Kafka degradation** -- remain validated locally against
Compose only, exactly as Milestone 15 left them. This is a named,
accepted gap, not silently dropped: `docs/runbooks/
eks-load-and-chaos-validation.md` states it explicitly, with the exact
reason (the `_docker_compose()` coupling above), so a future milestone
that wants real Kubernetes-native chaos testing starts from an honest
account of what exists today, not a rediscovery of this same finding.

**The runbook is the deliverable, not a code change.** Nothing in this
milestone has ever been run against a real cluster -- there is no real
EKS deployment yet (Milestone 31 is the first milestone with real AWS
credentials and a real deployment). The runbook documents the exact
commands and the claims each verifies so that once Milestone 31 makes a
real cluster and a real Ingress URL exist, running the load half of this
validation is a matter of following an already-reviewed procedure, not
inventing one under pressure.

## Alternatives considered

- **Build a Kubernetes-native chaos mechanism now**, so all five claims
  could be validated against EKS in this milestone. Rejected: a
  materially larger, genuinely new piece of work than what Milestone 30
  was scoped as, and a real architectural fork (which injection
  mechanism, how recovery is detected) not settled by any existing
  evidence -- the project owner's explicit choice was to keep this
  milestone to its original, smaller scope and treat real Kubernetes
  chaos tooling as future work if it's ever wanted.
- **Silently document only what's convenient** (i.e., write the runbook
  as if all five claims were extended, glossing over the chaos-half
  gap). Rejected outright: inconsistent with this project's standing
  practice of naming gaps explicitly (ADR-0006's outbox gap, ADR-0015's
  Kafka health-signal finding, Milestone 26's narrowed ML scope) rather
  than implying more was done than actually was.

## Acceptance criteria

No AWS account, credentials, real Kubernetes cluster, or cloud resource
of any kind is required or created by satisfying these criteria.

1. `docs/runbooks/eks-load-and-chaos-validation.md` exists, names all
   five claims from the original Milestone 30 scope, and states plainly
   which three are extended to EKS (via `load.py`) and which two are not
   (the `experiment.py` chaos half), with the reason.
2. No changes to `ops/chaos/experiment.py`'s actual behavior -- it
   continues to run only against Docker Compose, unchanged.
3. `simulator/load.py` requires no code changes to support a real
   `--base-url` -- confirmed by reading the existing CLI argument
   definition, not assumed.
4. Nothing in this milestone is executed against a real cluster; no AWS
   credentials are used or required.

## Consequences

**Positive**

- Three of five claims get a real, reviewed, ready-to-run procedure the
  moment a real EKS deployment exists, instead of that work happening
  ad hoc after Milestone 31.
- The `experiment.py`/Docker Compose coupling is now an explicit,
  documented fact instead of an assumption the roadmap got wrong once
  and might get wrong again.

**Negative, and accepted**

- Two of the five originally-scoped claims (fallback behavior, Kafka
  degradation) are not validated against real EKS by this milestone --
  named here as a real, accepted gap, not a silent reduction in scope.
- A future Kubernetes-native chaos mechanism, if ever built, starts from
  scratch -- this milestone does not scaffold one, even partially.
