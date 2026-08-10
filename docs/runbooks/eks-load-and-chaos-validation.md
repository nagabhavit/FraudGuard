# Runbook: load and chaos validation against the real EKS deployment

See ADR-0019 for the decision this runbook implements, including why it
covers three of Milestone 30's five originally-scoped claims, not all
five.

**Nothing in this runbook has ever been executed against a real
cluster.** There is no real EKS deployment yet -- Milestone 31 is the
first milestone in this project with real AWS credentials and a real
deployment. This document exists so that, once Milestone 31 makes a
real cluster and a real Ingress URL exist, running this validation is a
matter of following an already-reviewed procedure, not inventing one
under pressure. Every command below reuses `services/simulator/src/
simulator/load.py` (Milestone 15) exactly as it already exists --
nothing here requires a code change.

## Prerequisite

A real, reachable URL for the gateway's `Ingress` (`infra/k8s/
ingress.yaml`, Milestone 21) -- the ALB's DNS name, or a real domain
pointed at it once one exists (still undecided, per Milestone 21's own
TLS/domain deferral). Until that URL is real, none of the commands below
can run against anything but `docker compose` locally.

## What this runbook covers, and what it deliberately does not

| Claim | Tool | Extended to EKS this milestone? |
| --- | --- | --- |
| Latency (client-observed p50/p95/p99 vs. the hot-path budget) | `simulator/load.py` | Yes |
| Service availability under sustained load | `simulator/load.py` | Yes |
| Resource/autoscaling behavior (Milestone 22's HPA) | `simulator/load.py` | Yes |
| Fallback behavior (the degradation ladder) | `ops/chaos/experiment.py` | **No** -- see ADR-0019 |
| Kafka degradation | `ops/chaos/experiment.py` | **No** -- see ADR-0019 |

The last two remain validated locally against Docker Compose only
(Milestone 15's original scope), because `ops/chaos/experiment.py`
injects and recovers every outage via `docker compose stop`/`start` --
there is no Kubernetes-native equivalent in the script. Running
`ops/chaos/experiment.py --target model-service` (etc.) against a real
cluster today would simply fail to inject anything, not exercise the
real deployment. Do not attempt to point `experiment.py` at a real
`--gateway-url` expecting it to work -- the outage-injection half of the
script has no way to affect a real cluster's pods.

## Claim 1 & 2: latency and service availability under load

```
uv run --package fraudguard-simulator python -m simulator.load \
    --base-url https://<real-ingress-url> \
    --duration-seconds 60 \
    --concurrency 20
```

Reports `sent`/`succeeded`/`failed` and client-observed p50/p95/p99
latency (factory-to-response, including real network hops this time --
the first time this project's own latency claims are measured outside
`docker compose`, not against `localhost`).

**What to check:**
- `failed` should be 0, or explainable (a transient scale-up, not a
  sustained error rate) -- a nonzero, sustained failure rate under
  normal load is a real regression, not expected.
- p99 against the README's hot-path budget
  (`GatewaySettings.scoring_budget_ms`, 100ms) -- this is the first time
  that budget is checked against real infrastructure latency (VPC
  networking, the real ALB, real pod-to-pod calls) rather than Compose's
  loopback network, so a real, if modest, latency increase relative to
  local runs is expected and not itself a failure.

## Claim 3: resource/autoscaling behavior

Milestone 22's `infra/k8s/hpa.yaml` set `minReplicas: 1, maxReplicas: 3,
targetCPUUtilizationPercentage: 70` for every app service -- explicitly
marked illustrative, not load-test-derived, pending this validation.

While a `--duration-seconds 60 --concurrency 20` (or higher) run from
Claim 1/2 is in progress, watch each Deployment's replica count:

```
kubectl get hpa -n fraudguard --watch
kubectl get pods -n fraudguard --watch
```

**What to check:**
- Whether CPU utilization actually approaches the 70% target under this
  load, or whether the illustrative `resources.requests`/`limits`
  values (`infra/k8s/gateway.yaml` etc., also Milestone 22) are too
  generous or too tight for real traffic -- either way, this is real
  evidence to revise those illustrative numbers with, which is exactly
  what Milestone 22's own documentation said this validation step was
  for.
- Whether a scale-up event correlates with any latency degradation or
  request failures from Claim 1/2 (new pods becoming ready takes real
  time; the HPA's default behavior does not guarantee zero-disruption
  scaling).

## Claims 4 & 5: fallback behavior and Kafka degradation (not covered here)

Continue running these locally, exactly as Milestone 15 established:

```
uv run --all-packages python ops/chaos/experiment.py --target model-service
uv run --all-packages python ops/chaos/experiment.py --target feature-service
uv run --all-packages python ops/chaos/experiment.py --target kafka
```

See `ops/chaos/experiment.py`'s own module docstring and ADR-0015 for
what each verifies, including the Kafka target's documented
`checks.kafka_consumer` limitation (verified and printed on every run,
not a pass/fail signal -- `fraudguard_gateway_kafka_publish_total{outcome}`
is). Extending these to a real Kubernetes-native outage mechanism is
future work, not scoped by this milestone (ADR-0019).
