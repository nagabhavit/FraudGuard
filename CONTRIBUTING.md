# Contributing to FraudGuard

This document is the engineering contract for the repository. It is written for
a team even though the team is currently small — the conventions are what keep
the project reviewable as it grows.

---

## Local setup

Prerequisites: Docker Engine 24+ with Compose v2, [uv](https://docs.astral.sh/uv/),
and Node 20+ (for the dashboard, once it exists).

```bash
cp .env.example .env
uv sync --all-packages --all-groups      # creates .venv from uv.lock, exactly reproducible
uv run pre-commit install --install-hooks
docker compose up -d      # infrastructure only
docker compose ps         # every service must report (healthy)
```

`pre-commit install` wires both the `pre-commit` and `commit-msg` hooks, so
commit messages are validated against the convention below at the moment you
write them.

`uv` reads `.python-version` and provisions Python 3.12 itself. You do not need
a system Python matching that version.

`--all-packages` is not optional. The workspace root is `package = false` with
no dependencies, so a plain `uv sync` installs only the dev groups and none of
the workspace members' runtime dependencies — `mypy` then fails to import the
Pydantic plugin. `--all-packages` installs every member; `--all-groups` adds the
development toolchain.

---

## Working with the uv workspace

The workspace root has one `uv.lock` covering every member. Each member declares
its own dependencies in its own `pyproject.toml`.

```bash
# Add a runtime dependency to one service
uv add --package fraudguard-gateway 'redis>=5.2'

# Add a development-only tool, available to the whole workspace
uv add --group dev 'pytest-benchmark'

# Install exactly one service's dependency subtree (what Dockerfiles do)
uv sync --frozen --package fraudguard-gateway --no-dev

# Refresh the lockfile after editing a pyproject.toml by hand
uv lock
```

Never edit `uv.lock` by hand, and never run `uv lock --upgrade` inside a feature
PR — dependency upgrades belong in their own commit so a regression bisects
cleanly.

---

## Quality gates

Two layers, with different jobs. See
[ADR-0004](docs/adr/0004-quality-gates.md).

| Layer | Runs on | Enforces |
| --- | --- | --- |
| pre-commit | changed files, locally, in seconds | whitespace, YAML/TOML validity, ruff, secrets, lockfile drift, commit format, mypy |
| GitHub Actions | everything, from a clean checkout | all of the above plus tests, coverage floor, and dependency audit |

Pre-commit is a convenience and can be bypassed with `--no-verify`. CI is the
gate and cannot. CI re-runs every hook with `pre-commit run --all-files`, so a
bypassed commit is still caught before merge.

Run the full local gate at any time:

```bash
uv run pre-commit run --all-files
uv run pytest --cov
```

The `mypy` hook runs against the real workspace environment rather than an
isolated one, so it requires `uv sync --all-packages --all-groups` to have been
run. If it fails with an import error, that sync is what is missing.

## Commit convention

[Conventional Commits](https://www.conventionalcommits.org/). The format is
mechanical because tooling reads it: changelog generation and semantic version
bumps are derived from these messages.

```
<type>(<scope>): <subject>
```

**Types:** `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `build`, `ci`,
`chore`, `revert`

**Scopes:** `common`, `gateway`, `features`, `model`, `aggregator`, `labels`,
`alerts`, `simulator`, `dashboard`, `ml`, `db`, `infra`, `ops`, `deps`

Subject is imperative mood, lowercase, no trailing period, under 72 characters.
A breaking change appends `!` after the scope and explains the break in the body.

```
feat(gateway): add redis token-bucket rate limiting
fix(aggregator): prevent duplicate window writes on offset replay
perf(features): pipeline redis reads into a single round-trip
feat(model)!: require feature schema hash at load time
```

The scope list is **enforced** by the `commit-msg` hook, not merely
documented — an unrecognised scope is rejected. This keeps scopes a closed
vocabulary that changelog tooling can group on. Adding a scope means editing
`.pre-commit-config.yaml` and this table together.

Known limitation: the hook is case-insensitive on the type, so `FEAT:` is
accepted. Use lowercase.

**Branches:** `feat/short-description`, `fix/short-description`,
`chore/short-description`.

---

## When an ADR is required

An Architecture Decision Record is mandatory — in the same pull request as the
change — for any of the following:

- Adding, removing, or merging a service boundary.
- Changing a Kafka topic's schema, key, partition count, or retention.
- Changing a data store, or how an existing store is used (for example moving a
  feature from Redis to Postgres).
- Changing the latency budget, an SLA, or a rung of the degradation ladder.
- Changing delivery semantics, idempotency strategy, or failure policy.
- Adding a runtime dependency that is hard to remove later.

ADRs live in `docs/adr/`, numbered sequentially, and follow the template of
`0001-record-architecture-decisions.md`. They record **context, decision,
alternatives considered, and consequences**. The alternatives section is the
one with value — an ADR that lists no rejected option is a description, not a
decision.

ADRs are immutable once accepted. To reverse one, write a new ADR that
supersedes it and mark the old one `Superseded by ADR-00NN`.

---

## Pull request checklist

Before requesting review:

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean
- [ ] `uv run mypy .` is clean, with no new `# type: ignore` lacking an
      explanatory comment
- [ ] New public functions and classes have docstrings explaining *why*, not
      *what* — the code already says what
- [ ] Any database migration is reversible and tested in both directions
- [ ] Any new configuration variable is added to `.env.example` with a comment
- [ ] An ADR is included if the change meets any criterion above
- [ ] The commit message follows the convention above

---

## Definition of done for a milestone

A milestone is not complete until all of the following hold:

1. Tests pass and cover the failure paths, not only the happy path.
2. Lint and type checks are clean.
3. The documented test procedure in the milestone description has been executed
   and the results match.
4. `docker compose up -d` from a clean state still reaches a healthy stack.
5. Work is committed with a conventional commit message.

---

## Code standards

**Type hints are mandatory.** `mypy --strict` runs in CI. This is enabled from
the first commit because retrofitting strict typing onto a mature codebase is a
multi-week project.

**Comments explain reasoning.** A comment restating the code is noise. A comment
recording why a non-obvious choice was made is the most valuable line in the
file.

**Errors are typed.** Raise a specific exception from the service's error
taxonomy, never a bare `Exception`. Catching `Exception` requires a comment
justifying it.

**No blocking calls in async functions.** Ruff's `ASYNC` rules catch most cases,
but they do not catch a synchronous third-party client. In a service with a
100 ms p99 budget, one blocking call stalls the entire event loop.

**Configuration comes from the environment.** No hardcoded hosts, ports, or
credentials. Anything environment-specific is a setting with a documented
default.
