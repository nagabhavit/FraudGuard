# =============================================================================
# FraudGuard dashboard image.
# =============================================================================
#
# Two stages: the builder installs npm dependencies and produces a static
# `dist/` bundle; the runtime image serves only that bundle, never Node or
# the source tree. Unlike the Python services, this image needs no
# repository-root build context -- the dashboard has no shared `libs/`
# dependency (ADR-0003 excludes it from the uv workspace entirely) -- so its
# compose entry can use `context: ./dashboard` directly.
# =============================================================================

FROM node:22-slim AS builder

WORKDIR /app

# Copy manifests before source so `npm ci` is cached across builds that only
# change application code.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Baked in at build time, not read at container startup: Vite inlines
# import.meta.env.* into the static bundle, so there is no process left at
# runtime to read an environment variable from. docker-compose.yml passes
# this as a build arg derived from GATEWAY_PORT, so the two stay in step
# without hardcoding the port twice.
ARG VITE_GATEWAY_URL=http://localhost:8000
ENV VITE_GATEWAY_URL=${VITE_GATEWAY_URL}
RUN npm run build

# nginx-unprivileged, not plain nginx: the plain image's master process runs
# as root even though workers drop to an unprivileged user. This image runs
# entirely as a non-root user and already listens on 8080 by default --
# matching DASHBOARD_PORT (.env.example) without a custom nginx.conf.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

# 127.0.0.1, not localhost: this image's /etc/hosts resolves "localhost" to
# ::1 first, and nginx here only binds the IPv4 wildcard -- wget then fails
# fast with "connection refused" even though the server is healthy, observed
# directly while verifying this container against the real compose stack.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
