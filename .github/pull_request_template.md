## What and why

<!-- What changed, and what problem it solves. Link the milestone or issue. -->

## How it was tested

<!-- Concrete steps and results, not "tested locally". -->

## Checklist

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean
- [ ] `uv run mypy .` is clean, with no new `# type: ignore` lacking a comment
- [ ] `uv lock --check` passes (lockfile matches `pyproject.toml`)
- [ ] New configuration variables are documented in `.env.example`
- [ ] Database migrations are reversible and tested in both directions
- [ ] Commit messages follow Conventional Commits

## Architecture decision record

An ADR is required for changes to a service boundary, a Kafka topic's schema or
partitioning, a data store, the latency budget, delivery semantics, or the
failure policy. See `CONTRIBUTING.md`.

- [ ] Not required for this change
- [ ] ADR included in this pull request: `docs/adr/____`
