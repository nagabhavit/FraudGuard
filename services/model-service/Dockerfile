# =============================================================================
# FraudGuard model-service image.
# =============================================================================
#
# Built from the repository root (see docker-compose.yml's `context: .`) so
# this stage can copy both services/model-service/ and the shared libs/
# tree -- see ADR-0002. Two stages: the builder resolves and installs this
# service's dependency subtree from the shared lockfile; the runtime image
# carries only the resulting virtualenv, not uv itself or the source tree
# twice over.
#
# The trained model artifact (ml/models/) is deliberately NOT copied into
# this image -- it is gitignored (.gitignore: model artifacts are versioned
# by content, not by git) and bind-mounted read-only at container start
# instead (docker-compose.yml). Retraining then takes effect on the next
# container restart, no image rebuild required. If no model is present, the
# service fails fast at startup (ADR-0009) and docker-compose.yml's
# `restart: unless-stopped` retries it until one is.
# =============================================================================

FROM ghcr.io/astral-sh/uv:0.9.9-python3.12-bookworm-slim AS builder

WORKDIR /app

# Copy the whole workspace's dependency manifests before any source, so
# `uv sync` is cached across builds that only change application code.
COPY pyproject.toml uv.lock ./
COPY libs/fraudguard-common/pyproject.toml libs/fraudguard-common/pyproject.toml
COPY libs/fraudguard-ml/pyproject.toml libs/fraudguard-ml/pyproject.toml
COPY services/model-service/pyproject.toml services/model-service/pyproject.toml

# --no-install-project defers installing the workspace members themselves
# until their source is present, while still resolving and caching every
# third-party dependency from the manifests copied above.
RUN uv sync --frozen --package fraudguard-model-service --no-dev --no-install-project

COPY libs/fraudguard-common libs/fraudguard-common
COPY libs/fraudguard-ml libs/fraudguard-ml
COPY services/model-service services/model-service

# --no-editable: the image ships a real installed wheel, not a path link back
# into a source tree that this stage is about to discard.
RUN uv sync --frozen --package fraudguard-model-service --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime

# LightGBM's compiled extension is linked against libgomp (OpenMP); the
# slim base does not include it, and without it "import lightgbm" fails at
# startup, not at build time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Never run a network-facing process as root -- a container escape from a
# root process is a host compromise, not just a container compromise.
RUN groupadd --system fraudguard && useradd --system --gid fraudguard fraudguard

COPY --from=builder --chown=fraudguard:fraudguard /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1" \
    MODEL_PATH="/app/ml/models/fraud_model.txt" \
    MODEL_METADATA_PATH="/app/ml/models/fraud_model.meta.json"

USER fraudguard
WORKDIR /app

EXPOSE 8003

# curl is not in the slim base and adding it costs image size for one probe;
# the standard library can make the same request.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8003/health/live', timeout=2)" || exit 1

# --no-access-log: RequestContextMiddleware already emits one structured JSON
# line per request. Uvicorn's own access logger writes a second, plain-text
# line for the same request, which is redundant and breaks the "every line is
# JSON" invariant the rest of the logging is built on.
CMD ["uvicorn", "model_service.asgi:app", "--host", "0.0.0.0", "--port", "8003", "--no-access-log"]
