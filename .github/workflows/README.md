# Workflows

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `ci.yml` | push to main, pull request | Lockfile, lint, type check, tests, integration tests (Postgres, Redis, Kafka, Schema Registry, feature-service, model-service), pre-commit hooks |
| `security.yml` | push, pull request, weekly | Dependency audit and secret scanning |

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

Actions are referenced by major version tag. Dependabot (`.github/dependabot.yml`)
proposes updates weekly. For a repository handling production payment traffic,
the next hardening step is pinning to full commit SHAs so a compromised or
retagged action cannot alter the build — that is scheduled with the deployment
pipeline work in Milestone 31.
