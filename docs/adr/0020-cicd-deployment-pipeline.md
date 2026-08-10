# ADR-0020: CI/CD deployment pipeline

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

Milestone 31 was named, by the repository itself, since Milestone 16:
`.github/workflows/README.md` already scheduled Action SHA-pinning here
("that is scheduled with the deployment pipeline work in Milestone 31"),
and every app-service Kubernetes manifest already named ECR publishing
here ("Publishing this to a real registry... is deployment-pipeline
work, Milestone 31"). This is the first milestone in the project's
entire history where real AWS credentials, real cost, and a real
deployment are legitimately in scope -- every milestone before it
(16-30) was deliberately plan/validate-only.

Investigation before implementation found the live repository state,
not assumed: zero ECR repositories, all 15 GitHub Actions `uses:`
references still major-version-tag-pinned, zero GitHub Environments
configured (`gh api repos/.../environments` → `"total_count":0`), and
`main` with no branch protection at all (`404 Branch not protected`) --
a real, pre-existing gap independent of this milestone, since the
README's own recommendations for it were never actually applied to the
live repository.

## Decision

**OIDC federation for AWS authentication, not long-lived access keys.**
Follows the exact pattern already established for every other AWS
identity in this project: Milestone 20's EKS OIDC provider (Kubernetes
ServiceAccounts), Milestone 21's Load Balancer Controller role,
Milestone 29's ESO role. `infra/terraform/github_oidc.tf` adds a
*second*, separate OIDC provider (`token.actions.githubusercontent.com`
-- a different issuer and trust boundary than the EKS cluster's own),
and **two** narrowly-scoped IAM roles, not one: `github_actions_ecr_push`
(trust condition: OIDC `sub` = `repo:nagabhavit/FraudGuard:ref:refs/heads/main`;
permissions: ECR push only) and `github_actions_deploy` (trust
condition: `sub` = `repo:nagabhavit/FraudGuard:environment:production`;
permissions: `eks:DescribeCluster` plus an EKS access entry granting
`AmazonEKSEditPolicy`, scoped to the cluster). Neither role can do what
the other can -- no GitHub Actions job ever holds both ECR push and EKS
deploy permissions at once. No AWS access key is ever generated, stored
as a GitHub secret, or exposed in any log.

**Immutable, Git-commit-SHA image tags -- never `latest`.**
`infra/terraform/ecr.tf` sets `image_tag_mutability = "IMMUTABLE"` on
all five repositories; `.github/workflows/deploy.yml` tags every build
with `${{ github.sha }}`. An immutable tag cannot be silently
overwritten to point at different image content after the fact, which
is the entire point of tagging by commit SHA rather than a floating
label like `latest` -- the image a pod is running can always be traced
back to the exact commit that produced it.

**A manual approval gate before any real deployment, structurally
enforced two ways, not one.** `deploy.yml`'s `deploy` job references a
`production` GitHub Environment (the mechanism GitHub itself provides
for required-reviewer gates) -- but per the decision below, that
environment is not created for real by this milestone, so it provides
no actual protection yet. The real, present-today safety mechanism is
that **both jobs trigger on `workflow_dispatch` only**, not `push` --
nothing in this workflow can execute at all without a human explicitly
running it, a deliberately more conservative design than a typical
production pipeline (which would usually build-and-push automatically
on every merge to main). This is intentionally layered, not relying on
either mechanism alone: even a manually-dispatched run today would fail
immediately at the "configure AWS credentials" step, since
`AWS_ECR_PUSH_ROLE_ARN`/`AWS_DEPLOY_ROLE_ARN` secrets and an
`ECR_REGISTRY` variable do not exist in this repository yet either.

**Live GitHub Environment creation is deliberately deferred, not done
by this milestone.** `gh` CLI access in this environment is
authenticated with `repo` scope -- technically capable of creating a
real Environment and configuring required reviewers via the API right
now. This milestone does not do so. Creating a real, shared,
persistent GitHub repository setting is exactly the class of action
this project's standing execution discipline treats as needing
explicit, separate authorization -- distinct in kind from every
Terraform/Kubernetes change in Milestones 16-30, all of which were
local files, never applied, and fully reversible by construction. The
project owner will configure the real `production` Environment and its
required reviewers as a separate, later, manual step.

**Branch protection remains untouched, out of scope for this
milestone.** The live gap found during investigation (`main` has no
protection configured, despite the README's own long-standing
recommendation) is real and pre-existing, but is not part of what
Milestone 31 was ever scoped to deliver -- expanding this milestone to
fix it would be scope creep into a separate, already-named gap, not a
deployment-pipeline requirement. Named here so it is not lost, not
fixed here.

## Alternatives considered

- **Long-lived AWS access keys stored as GitHub secrets.** Rejected:
  the exact standing credential this project's IRSA-everywhere posture
  has consistently avoided since Milestone 20 -- a leaked key has no
  expiry and no automatic scope narrowing, unlike a federated,
  per-job-assumed role.
- **One IAM role for both build-and-push and deploy.** Rejected: same
  least-privilege reasoning as every other role in this project
  (Milestones 20, 21, 29 each scoped narrowly to one concern) -- a
  compromised or misconfigured build step should not be able to reach
  the cluster, and vice versa.
- **Automatic build-and-push on every push to main**, the more typical
  real-world pipeline shape. Rejected for this milestone specifically:
  given this is the first-ever real-AWS-credential milestone in the
  project, the more conservative `workflow_dispatch`-only design was
  chosen deliberately; switching to automatic triggering once real
  secrets exist is a natural, simple, separate future change.
- **Creating the live GitHub Environment and configuring required
  reviewers now**, since `gh` access technically allows it. Rejected:
  a real, shared, external state change outside this project's
  established "local file, never applied, fully reversible" pattern --
  reserved as the project owner's own explicit, separate action.
- **Expanding this milestone to also configure branch protection**,
  since it was discovered during investigation. Rejected: a genuinely
  separate gap, not part of Milestone 31's own scope; naming it here is
  sufficient, fixing it is not this milestone's job.

## Acceptance criteria

No AWS account, credentials, real Kubernetes cluster, real GitHub
Environment, or cloud resource of any kind is required or created by
satisfying these criteria.

1. `terraform init -backend=false` and `terraform validate` exit 0 for
   `ecr.tf` and `github_oidc.tf`.
2. `actionlint` exits 0 for `deploy.yml` and the two SHA-pinned existing
   workflows.
3. Every `uses:` reference across all three workflow files is a full
   commit SHA with a `# vX.Y.Z` comment, each SHA verified against the
   real upstream repository immediately before implementation, not
   invented.
4. `kubectl apply --dry-run=client` exits 0 for all five updated
   application manifests.
5. No live GitHub Environment or branch protection rule is created or
   modified by this milestone -- verified via read-only `gh api` calls
   before and after.
6. `deploy.yml`'s jobs trigger only on `workflow_dispatch`; no `push`
   or `workflow_run` trigger exists anywhere in the file.

## Consequences

**Positive**

- The deployment pipeline's IAM shape (OIDC, two narrowly-scoped roles,
  immutable SHA tags) is fully reviewed and ready the moment the project
  owner decides to apply the Terraform and configure the remaining
  manual steps -- no design work left for that moment.
- Consistent with this project's identity model end to end: every AWS
  principal in the entire system (EKS ServiceAccounts, GitHub Actions
  jobs) is federated, never a standing credential.

**Negative, and accepted**

- The pipeline cannot do anything today -- by design, not as an
  oversight -- until a real, separate sequence of manual steps happens
  (Terraform apply, repository secrets/variables, live Environment
  configuration). This milestone produces a complete, reviewed plan,
  not a working pipeline.
- Branch protection's pre-existing gap remains open, named but
  unresolved.
