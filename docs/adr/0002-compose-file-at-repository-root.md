# ADR-0002: Keep the Compose file at the repository root

- **Status:** Accepted
- **Date:** 2026-08-06

## Context

The initial architecture placed `docker-compose.yml` under `infra/docker/`,
grouping it with Terraform and Kubernetes manifests as "infrastructure". That
grouping is conceptually tidy but has two practical costs.

First, Compose resolves relative build contexts against the location of the
Compose file. From `infra/docker/`, every `context:` becomes `../../`, and the
gateway image — which must copy both `services/gateway/` and the shared
`libs/` — becomes awkward to express and easy to get wrong.

Second, every ad-hoc command needs a `-f` flag. In practice this means a
wrapper script becomes the only supported entry point, and typing
`docker compose ps` directly stops working. Tooling that only functions through
a wrapper is tooling people work around.

## Decision

`docker-compose.yml` lives at the repository root. `infra/` holds Terraform and
Kubernetes manifests only.

## Alternatives considered

- **Keep it in `infra/docker/` and set `COMPOSE_FILE` in `.env`.** Rejected:
  it works, but it makes the behaviour of `docker compose` depend on invisible
  environment state, which is confusing for anyone cloning the repository.
- **Keep it in `infra/docker/` and wrap the flag in a Makefile.** Rejected for
  the reason above, and because we have deliberately chosen not to add a
  Makefile.

## Consequences

- `docker compose up` works from the repository root with no flags.
- Build contexts are the repository root, so a service image can copy both its
  own directory and the shared `libs/` tree.
- `infra/` is unambiguously about cloud infrastructure, which makes its
  ownership boundary clearer.
