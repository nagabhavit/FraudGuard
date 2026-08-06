# ADR-0004: Split quality gates between pre-commit and CI

- **Status:** Accepted
- **Date:** 2026-08-06

## Context

FraudGuard needs automated quality gates before application code exists,
because retrofitting a linter, a strict type checker, or a coverage floor onto
a mature codebase is a multi-week project that competes with feature work and
usually loses.

Two mechanisms are available and they are frequently conflated:

- **pre-commit** runs on the developer's machine against changed files. It is
  fast, but it can be bypassed with `git commit --no-verify`, and it runs in
  whatever environment the developer happens to have.
- **GitHub Actions** runs from a clean checkout against everything. It is
  slower, but it cannot be bypassed and its environment is reproducible.

Treating these as interchangeable produces one of two failure modes: enforcing
everything locally makes commits slow enough that people bypass the hooks, or
enforcing everything only in CI wastes a round-trip on trailing whitespace.

## Decision

**Pre-commit is a convenience. CI is the gate.** Every check that must not
reach `main` runs in CI. Pre-commit runs the subset that is fast enough to be
worth catching earlier, and CI re-runs all hooks with `pre-commit run
--all-files` so that a bypassed commit is still caught.

Three specific decisions follow.

### 1. mypy runs as a `local` hook, not via `mirrors-mypy`

`mirrors-mypy` installs mypy into a pre-commit-managed virtualenv that does not
contain FastAPI, Pydantic, or `fraudguard-common`. Every third-party symbol
resolves to `Any`, the hook reports success, and CI then fails on the same
code. A gate that passes on code the real gate rejects is worse than no gate,
because it trains people to distrust the tooling.

The `local` hook invokes `uv run --frozen mypy` against the actual workspace
environment. The cost is that it requires `uv sync --all-packages --all-groups`
to have been run first; that is an acceptable precondition and is documented in
`CONTRIBUTING.md`.

### 2. CI uses one aggregate gate job

Branch protection requires a single check named `CI`, which depends on every
other job. Requiring the individual jobs instead means every new job must also
be added to the repository settings by hand — a step that is forgotten, leaving
the new check advisory without anyone noticing.

The aggregate job explicitly fails on `cancelled` and `skipped` as well as
`failure`, because `needs` alone treats a skipped dependency as satisfied.

### 3. No Python version matrix

FraudGuard deploys on exactly one interpreter, pinned in `.python-version`.
Testing versions that will never ship consumes CI minutes and produces no
actionable signal.

## Alternatives considered

- **Pre-commit only, no CI checks.** Rejected: `--no-verify` exists, and hooks
  do not run on changes made through the GitHub web UI.
- **CI only, no pre-commit.** Rejected: a five-minute round-trip to learn about
  a missing newline is a bad trade when a one-second local hook exists.
- **`mirrors-mypy` with `additional_dependencies` listing every runtime
  package.** Rejected: it works, but the list is a second dependency
  specification that silently drifts from `pyproject.toml`, and it defeats the
  purpose of having a lockfile.
- **A single monolithic CI job.** Rejected: jobs run in parallel, so splitting
  reduces wall-clock time, and a failure is identifiable from the job name
  without opening the log.

## Consequences

**Positive**

- Cheap mistakes are caught in seconds; everything that matters is caught
  before merge regardless.
- `mypy --strict` and Conventional Commits are enforced from the first commit,
  when the cost of compliance is nearly zero.
- Adding a CI job requires no repository-settings change to become enforced.

**Negative, and accepted**

- The mypy hook is slower than the others and requires a synced environment.
  Contributors who have not run `uv sync` get a confusing failure; this is
  documented, and the CI job is the backstop.
- Pre-commit hook versions in `.pre-commit-config.yaml` must be kept in step
  with the `lint` dependency group by hand. Dependabot updates both, but they
  arrive as separate pull requests.
