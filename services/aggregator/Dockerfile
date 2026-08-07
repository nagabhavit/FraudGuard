# =============================================================================
# FraudGuard stream aggregator image.
# =============================================================================
#
# Built from the repository root (see docker-compose.yml's `context: .`) so
# this stage can copy both services/aggregator/ and the shared libs/ tree --
# see ADR-0002. Two stages: the builder resolves and installs this service's
# dependency subtree from the shared lockfile; the runtime image carries only
# the resulting virtualenv, not uv itself or the source tree twice over.
# =============================================================================

FROM ghcr.io/astral-sh/uv:0.9.9-python3.12-bookworm-slim AS builder

WORKDIR /app

# Copy the whole workspace's dependency manifests before any source, so
# `uv sync` is cached across builds that only change application code.
COPY pyproject.toml uv.lock ./
COPY libs/fraudguard-common/pyproject.toml libs/fraudguard-common/pyproject.toml
COPY libs/fraudguard-events/pyproject.toml libs/fraudguard-events/pyproject.toml
COPY libs/fraudguard-features/pyproject.toml libs/fraudguard-features/pyproject.toml
COPY services/aggregator/pyproject.toml services/aggregator/pyproject.toml

# --no-install-project defers installing the workspace members themselves
# until their source is present, while still resolving and caching every
# third-party dependency from the manifests copied above.
RUN uv sync --frozen --package fraudguard-aggregator --no-dev --no-install-project

COPY libs/fraudguard-common libs/fraudguard-common
COPY libs/fraudguard-events libs/fraudguard-events
COPY libs/fraudguard-features libs/fraudguard-features
COPY services/aggregator services/aggregator

# --no-editable: the image ships a real installed wheel, not a path link back
# into a source tree that this stage is about to discard.
RUN uv sync --frozen --package fraudguard-aggregator --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime

# Never run a network-facing process as root -- a container escape from a
# root process is a host compromise, not just a container compromise.
RUN groupadd --system fraudguard && useradd --system --gid fraudguard fraudguard

COPY --from=builder --chown=fraudguard:fraudguard /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1"

USER fraudguard
WORKDIR /app

EXPOSE 8002

# curl is not in the slim base and adding it costs image size for one probe;
# the standard library can make the same request.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8002/health/live', timeout=2)" || exit 1

# --no-access-log: RequestContextMiddleware already emits one structured JSON
# line per request. Uvicorn's own access logger writes a second, plain-text
# line for the same request, which is redundant and breaks the "every line is
# JSON" invariant the rest of the logging is built on.
CMD ["uvicorn", "aggregator.asgi:app", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]
