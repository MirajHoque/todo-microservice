# syntax=docker/dockerfile:1.7
# ============================================================
# Multi-stage Dockerfile for the web service (Next.js)
#
# Stage 1 (deps)    — install node_modules from package-lock.json
# Stage 2 (builder) — `next build` → .next/standalone
# Stage 3 (runtime) — only server.js + the files it needs
#
# The final image has no source code, no dev dependencies and
# no build tools — just Node and the standalone server.
#
# AUTH_URL / API_URL / AGENT_URL are NOT baked in: proxy.ts reads
# them when the container starts, so the same image runs anywhere:
#
#   docker build -t todo-web web/
#   docker run --rm -p 3000:3000 \
#     -e AUTH_URL=http://host.docker.internal:8081 \
#     -e API_URL=http://host.docker.internal:8080 \
#     -e AGENT_URL=http://host.docker.internal:8083 todo-web
#
# (host.docker.internal = "your Mac" as seen from inside a container;
# localhost there would mean the container itself.)
# ============================================================

# Keep the Node major in sync with local development (node -v).
# Pinned by digest so builds are reproducible — let
# Renovate/Dependabot bump the tag + digest together.
ARG NODE_IMAGE=node:26.13.0-alpine3.24@sha256:c6ad9e9c1d80f6eb607c26b4b0a132ff7a2344fad1c78ea3baa2a7d4c8de6d94

# ── Stage 1: Dependencies ────────────────────────────────────
FROM ${NODE_IMAGE} AS deps
WORKDIR /app

# Copy only the dependency files first — this layer is cached
# until package.json/package-lock.json change. `npm ci` installs
# exactly what the lock file says (like `go mod download`).
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
  npm ci

# ── Stage 2: Build ───────────────────────────────────────────
FROM ${NODE_IMAGE} AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Don't send anonymous usage data to Vercel during builds.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Stage 3: Runtime ─────────────────────────────────────────
FROM ${NODE_IMAGE} AS runtime

ARG VERSION=dev
ARG REVISION=unknown
LABEL org.opencontainers.image.title="todo-web" \
  org.opencontainers.image.source="https://github.com/MirajHoque/todo-microservice" \
  org.opencontainers.image.version="${VERSION}" \
  org.opencontainers.image.revision="${REVISION}"

WORKDIR /app

ENV NODE_ENV=production \
  NEXT_TELEMETRY_DISABLED=1 \
  PORT=3000 \
  HOSTNAME=0.0.0.0

# standalone/ has server.js and the traced node_modules. Static
# assets aren't included by Next.js, so copy them next to it —
# server.js then serves them itself.
COPY --from=builder --chown=1000:1000 /app/.next/standalone ./
COPY --from=builder --chown=1000:1000 /app/.next/static ./.next/static
COPY --from=builder --chown=1000:1000 /app/public ./public

# The base image's non-root "node" user. Numeric so Kubernetes
# `runAsNonRoot` can verify it.
USER 1000:1000

EXPOSE 3000

# No curl in the image — use Node itself to check the server answers.
# (On Kubernetes, use liveness/readiness probes instead.)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]

# Exec form — Node is PID 1 and receives SIGTERM directly.
CMD ["node", "server.js"]
