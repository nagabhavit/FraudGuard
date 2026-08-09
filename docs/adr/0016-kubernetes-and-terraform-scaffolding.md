# ADR-0016: Kubernetes and Terraform scaffolding

- **Status:** Accepted
- **Date:** 2026-08-09

## Context

`docs/architecture.md`'s roadmap bundles the remaining work into an
unscoped `16+` row inherited from the original `15+`/`12+` catch-all
("k8s/Terraform," Milestone 15 having just been split out as its own
milestone, ADR-0015). Unlike every prior "+" bundle this project has
unpacked, this one cannot be resolved by reading `docs/architecture.md`
alone: scattered comments elsewhere in the repository reference specific,
much higher milestone numbers with distinct, already-decided content --

- `.env.example`, `docker-compose.yml` (twice), and
  `fraudguard_common.settings` all reference **Milestone 29**: production
  configuration via AWS Secrets Manager injected at pod startup,
  production Kafka with 3 brokers (RF=3), and Grafana's production auth
  posture.
- `.github/workflows/README.md` references **Milestone 31**: the CI/CD
  deployment pipeline, including pinning GitHub Actions to commit SHAs.

This means the original roadmap author intended a much longer, more
granular sequence for "k8s/Terraform" than one milestone -- something
spanning at least 16 through 31, with 29 and 31 already claimed by
specific, later concerns. Milestones 17-28 and 30 have no defined scope
anywhere in this repository. Given every milestone in this project has
been "the smallest correct slice of an unscoped bundle, verified against
the real stack" (Milestones 12-15 each did exactly this), Milestone 16 is
scoped as the *first* slice: proving the shape of the eventual
Kubernetes/Terraform deployment is structurally correct, without
provisioning anything real, touching AWS credentials, or pulling forward
any of Milestone 29's or 31's already-claimed work.

Five things needed deciding before any file was worth writing: the AWS
compute target, which parts of the system get Kubernetes manifests this
milestone, how much Terraform to write and in what style, whether to
introduce new tooling for local validation, and how far this milestone's
Terraform reaches without ever running `apply`.

## Decision

**Milestone 16 is plan/validate-only. No AWS credentials are used
anywhere in this milestone; no `terraform apply`; no real AWS resource is
ever created.** `terraform init -backend=false && terraform validate` and
`kubectl apply --dry-run=client` are the only checks this milestone's
"done" depends on -- both require no cloud access at all. This mirrors
ADR-0015's reasoning for keeping load/chaos testing out of CI: adding a
real cloud dependency (credentials, a live cluster, real spend) is a
materially bigger step than anything this project has done, and is
exactly the kind of decision Milestones 29 (production config) and 31
(deployment pipeline) already exist to make deliberately, not as a side
effect of a scaffolding milestone.

**The intended compute target is Amazon EKS**, chosen explicitly (not
previously stated anywhere in the repository -- only "pod startup" and
"AWS Secrets Manager" hinted at *some* Kubernetes, on *some* cloud).
Nothing about this milestone provisions an EKS cluster; the Terraform in
`infra/terraform/` is a structurally valid *definition* of one, never
applied.

**`infra/terraform/` contains the smallest structurally-valid EKS cluster
skeleton, hand-written against the native `hashicorp/aws` provider -- no
Terraform Registry community modules.** A VPC with two public subnets
across two Availability Zones (the minimum EKS itself requires), an IAM
role and policy attachment for the control plane, and the
`aws_eks_cluster` resource wired to both. No node groups, no cluster
add-ons (VPC CNI, CoreDNS, kube-proxy), no OIDC provider for IRSA -- all
real, later decisions this milestone does not need to make to be a valid
cluster *definition*. The S3+DynamoDB remote-state backend `.gitignore`
already reserves (`.terraform/`, `*.tfstate` excluded, with a comment
naming "an encrypted S3 bucket with DynamoDB locking") is declared in
`versions.tf` but never initialized against -- `terraform init
-backend=false` is what this milestone's validation actually runs, which
skips backend initialization entirely.

**`infra/k8s/` contains Deployment + Service manifests for the five
containerized application services only** (`gateway`, `feature-service`,
`aggregator`, `model-service`, `dashboard`) **-- no datastores.**
Postgres, Redis, Kafka, and Schema Registry get no Kubernetes manifests
this milestone: `docker-compose.yml`'s own comments and Milestone 29's
"production Kafka uses 3 brokers" hint that at least Kafka's production
topology is a deliberate, later decision (very possibly a managed AWS
service, not a self-hosted StatefulSet) -- writing a Kafka StatefulSet
now would risk contradicting a decision this project hasn't made yet.
Each manifest translates its service's already-existing Dockerfile
`HEALTHCHECK` directly into `livenessProbe`/`readinessProbe` against the
exact same paths (`/health/live`, `/health/ready` for the four Python
services; `/` for the dashboard, a static nginx-served SPA with no
health route of its own) -- no new application code, no new endpoint.

**These manifests are honest structural skeletons, not functional
deployments.** Because datastores are out of scope, the four Python
services' manifests omit `POSTGRES_*`, `KAFKA_BOOTSTRAP_SERVERS`, and
`SCHEMA_REGISTRY_URL` entirely (present in `docker-compose.yml`'s
environment blocks, absent here) rather than inventing placeholder
values for infrastructure that doesn't exist. Applying any of these
manifests for real (not done in this milestone) would crash-loop on
first connection attempt -- the same fail-fast behavior
`docker-compose.yml`'s own services already have when a real dependency
is missing, not a new failure mode invented for Kubernetes. A single
shared `ConfigMap` carries only what's genuinely in scope: `LOG_LEVEL`,
and the in-cluster Service DNS URLs services call each other with
(`FEATURE_SERVICE_URL`, `MODEL_SERVICE_URL`, `DASHBOARD_ORIGIN` -- the
last a placeholder pending an Ingress/domain decision this milestone
does not make, since no Ingress resource is part of its scope either).
No Kubernetes `Secret` manifests exist: credential-bearing configuration
is explicitly Milestone 29's AWS Secrets Manager integration, not
reinvented here.

**Kubernetes manifest validation is `kubectl apply --dry-run=client`, not
a real cluster.** No `kind`/`minikube` is introduced -- this project has
never used either, and `--dry-run=client` needs nothing beyond `kubectl`
itself to check that every manifest is syntactically valid Kubernetes
API structure. A real (if local) cluster would validate more (that
references resolve, that the API server accepts the objects) but is new
tooling this milestone's "no new dependencies without asking" constraint
rules out introducing unasked.

**model-service's manifest omits `docker-compose.yml`'s model-file bind
mount entirely, rather than inventing a Kubernetes-native equivalent.** A
`PersistentVolume`, an init container pulling from object storage, or
baking the model into the image at build time are all real, later
decisions (model-registry territory the cold path's own description in
`docs/architecture.md` already gestures at) -- none made here.

**One ADR, not two**, matching every prior milestone's shape (Milestones
11 through 15 each got exactly one, regardless of how many pieces the
milestone touched).

## Acceptance criteria

No AWS account, credentials, real Kubernetes cluster, or cloud resource
of any kind is required or created by satisfying these criteria.

1. `terraform -chdir=infra/terraform init -backend=false` exits 0.
2. `terraform -chdir=infra/terraform validate` exits 0, with no AWS
   credentials present anywhere in the environment.
3. `kubectl apply --dry-run=client -f infra/k8s/` exits 0 for every
   manifest in the directory.
4. Every Python-service manifest's `livenessProbe`/`readinessProbe`
   paths and ports match exactly the `/health/live`/`/health/ready`
   paths and container port its own Dockerfile's `HEALTHCHECK` already
   uses; the dashboard manifest's probes match its Dockerfile's `/`
   check instead -- a structural cross-check against code that already
   exists, not a new claim about behavior.
5. Neither `terraform plan` nor `terraform apply` is run as part of
   "done." Their absence is the point, not a gap.

## Alternatives considered

- **Deferring all Kubernetes/Terraform work until Milestone 29 makes the
  compute-target and production-config decisions together.** Rejected:
  every other unscoped roadmap bundle in this project (dashboard, alerts,
  labels, load/chaos testing) got unpacked into its own milestone as soon
  as it could be scoped as a small, independently-verifiable slice; there
  is no reason this bundle should wait for a single mega-milestone when a
  plan-only skeleton is independently useful and verifiable now.
- **A Terraform Registry community module for the VPC/EKS cluster (e.g.
  `terraform-aws-modules/eks/aws`)** instead of hand-written resources.
  Rejected: idiomatic in production Terraform work, but an external
  dependency this project does not otherwise have, and the explicit
  instruction for this milestone was to avoid unnecessary third-party
  modules. Hand-written resources are also more legible for a portfolio
  project's own review, since nothing is hidden inside a module's
  internals.
- **Writing Kubernetes manifests (StatefulSets) for
  Postgres/Redis/Kafka/Schema Registry too**, so the manifest set could
  theoretically be applied and run standalone. Rejected: Milestone 29's
  own hints suggest at least Kafka's production topology is a deliberate
  later decision possibly involving a managed AWS service instead of a
  self-hosted StatefulSet; writing one now risks contradicting a decision
  not yet made, for a milestone that is validate-only and will never
  actually run these manifests regardless.
- **A local `kind` cluster for real (not dry-run) manifest validation.**
  Rejected for this milestone: more thorough, but a new tool this project
  has never used, and the explicit instruction was not to introduce one
  unless already configured. `kubectl apply --dry-run=client` is
  sufficient to prove the manifests are syntactically valid, which is
  this milestone's actual claim.
- **Inventing placeholder datastore connection values** (a fake
  `POSTGRES_HOST`, etc.) so the manifests "look complete." Rejected:
  dishonest about what this milestone actually provisions, and
  inconsistent with this project's established pattern (every ADR since
  0006 has been explicit about documented gaps rather than papering over
  them, e.g. ADR-0006's "persisted but never published" gap, ADR-0015's
  Kafka health-signal finding).

## Consequences

**Positive**

- The eventual Milestone 29/31 work has a concrete, reviewed starting
  shape to build on -- a real EKS cluster definition and real workload
  manifests, not a blank `infra/` directory -- without this milestone
  having taken on any of their actual scope or risk.
- Every manifest and Terraform resource directly reuses something that
  already exists (Dockerfiles, `HEALTHCHECK` paths, `.env.example`
  variable names, `.gitignore`'s own backend hint) rather than inventing
  new conventions -- consistent with this project's pattern of
  extending, not duplicating, existing design.
- Zero new risk: no credentials, no cloud spend, no real infrastructure
  exists as a result of this milestone, so there is nothing to
  accidentally leave running or misconfigure.

**Negative, and accepted**

- The Kubernetes manifests are not a working deployment -- applying them
  for real would crash-loop every Python service (no datastore) and
  leave the dashboard the only pod that could plausibly start.
  Documented explicitly in each manifest's own comments, not a silent
  gap.
- `terraform validate` proves internal syntactic and type consistency,
  not that the configuration would actually succeed against a real AWS
  account (which requires `plan`/`apply`, deliberately not run). A
  materially incomplete picture of "does this work," accepted because
  this milestone's entire point is the boundary between what's
  scaffolded and what's real.
- Milestones 17-28 and 30 remain completely unscoped after this
  milestone, exactly as before -- this ADR does not reduce that
  ambiguity, only Milestone 16's own small piece of it.
