# ADR-0003: Use a uv workspace with a single lockfile

- **Status:** Accepted
- **Date:** 2026-08-06

## Context

FraudGuard is a monorepo containing several independently deployable Python
services plus shared libraries. Two requirements appear to conflict:

1. Each service must be independently deployable, and its container image must
   contain only its own dependencies. The gateway image must not carry
   LightGBM.
2. Dependency resolution must be reproducible and auditable, so that what runs
   in production is exactly what was tested.

The naive reading is that requirement 1 demands one lockfile per service.

## Decision

Use a **uv workspace** with a single `uv.lock` at the repository root, where
each member declares its own dependencies in its own `pyproject.toml`.

The two requirements are reconciled at install time:

```bash
uv sync --frozen --package fraudguard-gateway --no-dev
```

This installs only the gateway's dependency subtree, resolved from the shared
lock. Independence of *images* does not require independence of *resolution*.

`uv.lock` is committed. Applications commit lockfiles; libraries do not.
FraudGuard is a deployable application monorepo.

The `dashboard/` directory is deliberately excluded from the workspace. It is
an npm project with its own `package-lock.json`; folding Node into the Python
lock buys nothing.

## Alternatives considered

- **One independent project per service, each with its own lockfile.** More
  flexible: services could run different versions of a shared dependency. This
  flexibility is the problem. Version skew across services makes
  `fraudguard-common` untestable — you can no longer say which version of
  Pydantic it is expected to work with. It also multiplies the CI matrix and
  the vulnerability-scanning surface by the number of services, so a single
  CVE becomes N pull requests.
- **A single flat `pyproject.toml` covering all services.** Rejected: every
  image would then contain every dependency, defeating requirement 1 entirely.
- **Poetry or PDM with a plugin for monorepos.** Rejected: workspaces are
  first-class in uv rather than bolted on, and uv resolves and installs an
  order of magnitude faster, which matters for CI wall-clock time.

## Consequences

**Positive**

- One resolution, so all services are guaranteed to run the same
  `fraudguard-common` and the same version of every shared dependency.
- One security-scanning surface; one Dependabot pull request per CVE.
- `uv sync --frozen` in CI and in Dockerfiles is byte-for-byte reproducible.
- Adding a service requires no edit to the root — `members` is glob-based.

**Negative, and accepted deliberately**

- All members resolve to the same version of any shared dependency. If one
  service genuinely required an older Pydantic than another, the workspace
  could not express it. This is treated as a feature: version skew inside a
  monorepo is a source of bugs that are difficult to reproduce.
- The escape hatch, if divergence ever becomes genuinely necessary, is to eject
  that service into its own project and depend on `fraudguard-common` through
  `[tool.uv.sources]` as a path dependency.
