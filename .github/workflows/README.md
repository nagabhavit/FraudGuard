# Workflows

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `ci.yml` | push to main, pull request | Lockfile, lint, type check, tests, integration tests (full stack: Postgres, Redis, Kafka, Schema Registry, gateway, feature-service, aggregator, model-service), pre-commit hooks |
| `security.yml` | push, pull request, weekly | Dependency audit and secret scanning |
| `deploy.yml` | `workflow_dispatch` only (Milestone 31) | Build and push images to ECR, then deploy to EKS behind a manual production approval. See ADR-0020 -- nothing in this workflow has ever run; it requires Terraform applied, repository secrets/variables configured, and a real GitHub Environment, none of which exist yet. |

## Branch protection

Configure `main` with exactly one required status check: **`CI`**.

`CI` is the aggregate gate job in `ci.yml`. It depends on every other job and
fails if any of them failed, was cancelled, or was skipped. Requiring the
aggregate rather than the individual jobs means a job added later is enforced
immediately, with no change to repository settings — a step that is otherwise
easy to forget, leaving new checks green-by-default.

Recommended settings:

- Require a pull request before merging, with 1 approval
- Require review from Code Owners
- Require status checks to pass: `CI`
- Require branches to be up to date before merging
- Require conversation resolution before merging
- Do not allow bypassing the above settings

## Action pinning

Every `uses:` reference across all three workflow files is pinned to a full
commit SHA, with a `# vX.Y.Z` comment recording the human-readable version —
so a compromised or retagged action cannot alter the build (Milestone 31,
ADR-0020). Dependabot (`.github/dependabot.yml`) still proposes updates
weekly against the SHA-pinned references, exactly as it did against tags.

## Deployment pipeline

`deploy.yml` exists and is fully reviewed but has never run — see ADR-0020
for the complete design (OIDC authentication, no long-lived AWS keys;
immutable Git-commit-SHA image tags; a manual approval gate). Before it can
do anything for real, someone with repository admin access must, as separate
manual steps this milestone deliberately does not perform:

1. Apply `infra/terraform/ecr.tf` and `infra/terraform/github_oidc.tf`
   against a real AWS account.
2. Configure this repository's `AWS_ECR_PUSH_ROLE_ARN` and
   `AWS_DEPLOY_ROLE_ARN` secrets, and an `ECR_REGISTRY` variable, from that
   Terraform's outputs.
3. Create a real `production` GitHub Environment and configure required
   reviewers on it.

Note: no manual step is needed for `infra/k8s/*.yaml`'s
`<ECR_REGISTRY>`/`<GIT_SHA>` placeholders — `deploy.yml`'s `kubectl set
image` step resolves them to real values at deploy time; the committed
manifests are never applied directly.
