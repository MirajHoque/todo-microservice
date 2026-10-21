# syntax=docker/dockerfile:1.7
# ============================================================
# Multi-stage Dockerfile for todo-app
#
# Stage 1 (builder) — full Go toolchain, compiles the binary
# Stage 2 (runtime) — distroless, only the binary
#
# Migrations and HTML templates are embedded in the binary
# (go:embed), so the runtime image needs nothing else.
#
# Build:
#   docker build --build-arg VERSION=$(git describe --tags --always) \
#                --build-arg REVISION=$(git rev-parse HEAD) -t todo-app .
# ============================================================

# Keep in sync with the `go` line in go.mod.
# Images are pinned by digest so builds are reproducible —
# let Renovate/Dependabot bump the tag + digest together.

# ARG is like variable, but its only avaiable during image build. 
ARG GO_IMAGE=golang:1.26.3-alpine3.22@sha256:be93003ee861b3b91b6ebcb22678524947e0cd786c2df3f32af520006b1e54f5
ARG RUNTIME_IMAGE=gcr.io/distroless/static-debian13:nonroot@sha256:e2e927ec666bae08560abb3c55d0659eceabb657f56b6782ab500a9fc7f555e3

# ── Stage 1: Build ───────────────────────────────────────────
# --platform=$BUILDPLATFORM runs the compiler natively (fast on
# Apple Silicon) and cross-compiles to TARGETOS/TARGETARCH.
FROM --platform=$BUILDPLATFORM ${GO_IMAGE} AS builder

WORKDIR /src

# Copy dependency files first — this layer is cached until
# go.mod/go.sum change. The cache mount keeps downloaded modules
# between builds, so a go.mod change only fetches what's new.
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
  go mod download && go mod verify

COPY . .

ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev

# CGO_ENABLED=0 — static binary, runs on distroless/static
# -trimpath     — strip local file paths (reproducible builds)
# -s -w         — strip symbol table and debug info
# -X            — stamp the version into main.version
RUN --mount=type=cache,target=/go/pkg/mod \
  --mount=type=cache,target=/root/.cache/go-build \
  CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
  go build -trimpath \
  -ldflags="-s -w -X main.version=${VERSION}" \
  -o /out/todo-app \
  ./cmd/server

# ── Stage 2: Runtime ─────────────────────────────────────────
# distroless/static: CA certs, tzdata, /etc/passwd and a non-root
# user (65532) — no shell, no package manager. Tiny attack surface.
FROM ${RUNTIME_IMAGE} AS runtime

ARG VERSION=dev
ARG REVISION=unknown
LABEL org.opencontainers.image.title="todo-app" \
  org.opencontainers.image.source="https://github.com/MirajHoque/Todo" \
  org.opencontainers.image.version="${VERSION}" \
  org.opencontainers.image.revision="${REVISION}"

WORKDIR /app

COPY --from=builder --chown=nonroot:nonroot /out/todo-app /app/todo-app

# Numeric UID so Kubernetes `runAsNonRoot` can verify it.
USER 65532:65532

EXPOSE 8080

# No wget/curl in distroless — the binary checks itself.
# (On Kubernetes, use liveness/readiness probes on /health and
# /health/ready instead; they ignore HEALTHCHECK.)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["/app/todo-app", "healthcheck"]

# Exec form — the app is PID 1 and receives SIGTERM directly,
# which triggers the graceful shutdown in main.go.
# Logs go to stdout/stderr; Alloy reads them via the Docker driver.
ENTRYPOINT ["/app/todo-app"]