# ADR-0018: Observability architecture for the EKS deployment

- **Status:** Accepted
- **Date:** 2026-08-10

## Context

`ops/prometheus/`, `ops/grafana/`, and `ops/alertmanager/` provision a full
Prometheus + Grafana + Alertmanager stack as code for local Docker Compose
(ADR-0010, ADR-0013) -- static `scrape_configs` targeting Compose's internal
service names, alert rules in `ops/prometheus/rules/fraudguard.rules.yml`, a
provisioned datasource and dashboard in Grafana, and a null-receiver
Alertmanager route. None of this addresses what happens once the deployment
target changes to EKS (Milestones 16-24): the Compose-based stack has no
relationship to a real cluster's own pods.

Milestone 25 was explicitly scoped, per prior planning, as a decision
milestone before any implementation: three real options exist for where
production observability lives, and nothing in the repository favored one
over another. That decision has now been made explicitly, by the project
owner, before any Kubernetes manifest in this milestone was written.

## Decision

**In-cluster, self-hosted Prometheus + Grafana + Alertmanager**, running as
Kubernetes workloads inside the EKS cluster, in a new `monitoring` namespace
-- not Amazon Managed Prometheus/Grafana, and not the existing Compose stack
left externally unchanged.

**Every existing Compose-based configuration is reused, not reinvented.**
The in-cluster Prometheus config, alert rules, Grafana datasource/dashboard
provisioning, and Alertmanager route are the same content as
`ops/prometheus/`, `ops/grafana/`, and `ops/alertmanager/` already define,
adapted only where the deployment target itself requires it:

- **Scrape discovery**: Compose's static `targets: ["gateway:8000", ...]`
  becomes Prometheus's native `kubernetes_sd_configs` (role: `pod`),
  filtered to the `fraudguard` namespace and relabeled from
  `prometheus.io/scrape`/`prometheus.io/port` pod annotations -- the same
  annotation convention `infra/k8s/lb-controller.yaml`'s own Helm-rendered
  Deployment already uses (`prometheus.io/scrape: "true"`), not a new
  pattern invented here. The four Python services' Deployment manifests
  gain these two annotations; the dashboard is not annotated -- it has no
  `/metrics` endpoint, unchanged from every prior milestone's treatment of
  it.
- **Alert rules**: `ops/prometheus/rules/fraudguard.rules.yml`'s content is
  reused verbatim in a ConfigMap -- same thresholds, same PromQL, same
  "illustrative, not incident-derived" caveat already documented there.
- **Grafana provisioning**: the datasource and dashboard-provider YAML, and
  the `fraudguard-overview.json` dashboard itself, are reused verbatim,
  mounted as ConfigMaps instead of bind-mounted files.
- **Alertmanager**: the same null-receiver route (ADR-0013's own documented,
  accepted "no real on-call" posture for a portfolio project) -- wiring a
  real receiver (Slack/email/PagerDuty) remains explicitly out of scope,
  unchanged from ADR-0013.

**No new external dependency.** Kubernetes-native service discovery is a
built-in Prometheus feature (`kubernetes_sd_configs`), not a new operator or
CRD -- the Prometheus Operator was deliberately not introduced, consistent
with this project's standing "no new dependencies without asking" posture
(ADR-0016, ADR-0017).

**Plan/validate-only, same as every milestone since 16.** No cluster add-on,
no `terraform apply`, no AWS credentials, no real Prometheus/Grafana/
Alertmanager instance exists because of this milestone --
`kubectl apply --dry-run=client` is the only validation this milestone's
"done" depends on.

## Alternatives considered

- **Amazon Managed Service for Prometheus + Amazon Managed Grafana.**
  Rejected for this milestone: consistent with Milestones 23-24's own
  preference for managed AWS services over self-hosting (RDS, ElastiCache,
  MSK), but a materially different integration model (remote-write, not
  local scrape) that would mean rewriting every existing Compose config
  rather than reusing it, plus new, ongoing AWS cost. The project owner
  explicitly chose the closer-to-current-architecture option instead.
- **External, Compose stack left unchanged**, pointed at the EKS cluster's
  services over the network. Rejected: architecturally awkward for a
  deployment meant to stand on its own, and never seriously considered once
  the in-cluster option was chosen.
- **The Prometheus Operator** (CRD-based `ServiceMonitor`/`PodMonitor`
  resources) instead of static `kubernetes_sd_configs`. Rejected: a new
  third-party dependency (its own CRDs and controller) for a project that
  has consistently avoided introducing one without being forced to
  (Milestone 21's cert-manager investigation being the clearest precedent)
  -- native `kubernetes_sd_configs` achieves the same discovery outcome
  with zero new dependencies.

## Acceptance criteria

No AWS account, credentials, real Kubernetes cluster, or cloud resource of
any kind is required or created by satisfying these criteria.

1. `kubectl apply --dry-run=client` exits 0 for every new manifest in
   `infra/k8s/`.
2. Prometheus's scrape config uses `kubernetes_sd_configs`, not a static
   target list.
3. Alert rule content is byte-for-byte identical to
   `ops/prometheus/rules/fraudguard.rules.yml`.
4. Grafana's datasource and dashboard provisioning content is byte-for-byte
   identical to their `ops/grafana/provisioning/` and
   `ops/grafana/dashboards/` sources.
5. No `terraform plan`/`apply`; no cluster add-on or third-party
   operator/CRD introduced.

## Consequences

**Positive**

- Every piece of existing Prometheus/Grafana/Alertmanager configuration
  work (ADR-0010, ADR-0013) is reused, not duplicated or reinvented --
  the two stacks (Compose, in-cluster) stay in sync by construction as long
  as future changes are made to the shared source content.
- Zero new third-party dependency: native Kubernetes service discovery,
  not an operator.

**Negative, and accepted**

- Self-hosting Prometheus/Grafana/Alertmanager inside the cluster carries
  real operational burden (storage, upgrades, scaling) that a managed
  service would have absorbed -- accepted, per the project owner's explicit
  choice.
- The Compose-based and in-cluster configurations are two separate copies
  of logically the same content (scrape config, rules, dashboards) --
  keeping them in sync is a manual discipline this ADR does not automate.
