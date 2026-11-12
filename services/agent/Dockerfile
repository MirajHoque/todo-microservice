# syntax=docker/dockerfile:1.7
# ============================================================
# Multi-stage Dockerfile for the agent service (Python / FastAPI)
#
# Stage 1 (builder) — uv installs the dependencies and the agent
#                     package into /app/.venv (from uv.lock, exactly)
# Stage 2 (runtime) — a clean Python image + that .venv, nothing else
#
# The final image has no uv, no dev dependencies (pytest, ruff), no
# tests and no .env — settings come from environment variables:
#
#   docker build -t todo-agent services/agent/
#   docker run --rm -p 8083:8083 \
#     --env-file services/agent/.env \
#     -e ENV=production \
#     -e DATABASE_URL=postgresql://agent:agent@host.docker.internal:5433/agent_db \
#     -e TODO_URL=http://host.docker.internal:8082 \
#     todo-agent
#
# (--env-file brings JWT_SECRET, OPENROUTER_API_KEY, …. The -e flags
# override what must differ in a container: ENV (your .env says
# development = auto-reload), and the addresses — inside a container,
# localhost is the container itself; host.docker.internal is "your Mac".)
# ============================================================

# Keep the Python version in sync with .python-version, and uv with
# the version you use locally (uv --version). Pinned by digest so
# builds are reproducible — let Renovate/Dependabot bump tag + digest.
ARG PYTHON_IMAGE=python:3.15.2-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490

FROM ${UV_IMAGE} AS uv

# ── Stage 1: Build ───────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS builder

# uv is a single binary: copy it in instead of pip-installing it.
COPY --from=uv /uv /usr/local/bin/uv

# COMPILE_BYTECODE: write .pyc files now → faster container start.
# LINK_MODE=copy: real files in .venv (the cache is a separate mount).
# PYTHON_DOWNLOADS=never: use the image's Python, never download one.
ENV UV_COMPILE_BYTECODE=1 \
  UV_LINK_MODE=copy \
  UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 1) Dependencies only — this layer is cached until pyproject.toml or
#    uv.lock change, so editing code doesn't reinstall everything.
#    --locked: fail if uv.lock is out of date (never resolve anew).
#    --no-dev: no pytest/ruff in production.
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --locked --no-dev --no-install-project

# 2) Our code. --no-editable installs the agent package INTO .venv
#    (not a link back to src/), so the runtime stage needs only .venv.
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --no-dev --no-editable

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS runtime

ARG VERSION=dev
ARG REVISION=unknown
LABEL org.opencontainers.image.title="todo-agent" \
  org.opencontainers.image.source="https://github.com/MirajHoque/todo-microservice" \
  org.opencontainers.image.version="${VERSION}" \
  org.opencontainers.image.revision="${REVISION}"

WORKDIR /app

# Owned by root and read-only for the app user: the service can't
# modify its own code, even if something goes wrong.
COPY --from=builder /app/.venv /app/.venv

# .venv/bin first on PATH → `python` is the venv's python.
# ENV=production: no auto-reload, no /docs. PYTHONUNBUFFERED: logs
# appear immediately in `docker logs`.
ENV PATH="/app/.venv/bin:${PATH}" \
  PYTHONUNBUFFERED=1 \
  ENV=production \
  HOST=0.0.0.0 \
  PORT=8083

# A non-root user. Numeric so Kubernetes `runAsNonRoot` can verify it
# (same UID as the web image).
USER 1000:1000

EXPOSE 8083

# No curl in the image — use Python itself to check the server answers.
# (On Kubernetes, use liveness/readiness probes instead.)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8083/health', timeout=3)"]

# Exec form — Python is PID 1 and receives SIGTERM directly, so
# uvicorn shuts down gracefully (closes the pool, finishes requests).
CMD ["python", "-m", "agent"]
