# Roadmap: monolith → microservices on AKS

This repo started as a copy of the `todo-app` monolith (tag `v1-monolith`)
and is being transformed step by step into microservices running on
Azure Kubernetes Service. The app must keep working after every step.

## Target architecture

| Service | Language | Owns | Notes |
|---|---|---|---|
| `web` | Next.js (TypeScript) | nothing (UI only) | Calls the APIs over HTTP |
| `services/auth` | Go | `auth_db.users` | Register, login, issues JWTs |
| `services/todo` | Go | `todo_db.todos` | Todo CRUD |
| `services/agent` | Python (FastAPI) | `agent_db.conversations` | Orchestrator + agents; tools call todo-service's HTTP API with the user's JWT |

Routing (via Gateway API): `/` → web, `/api/auth` → auth, `/api/todos` → todo, `/api/agent` → agent.

## Rules

1. **Each service is self-contained**: its own `go.mod`/`pyproject.toml`/`package.json`, Dockerfile, migrations and `.env`.
2. **No importing another service's code.** Services talk only over HTTP (contract: OpenAPI).
3. **Each table has exactly one owner.** Other services go through the owner's API — no shared tables.
4. **Shared code is generic only** (logger, HTTP middleware, JWT verify) and lives in `libs/`. Nothing that knows about users or todos.
5. **Every service deploys independently**: own image, own Deployment, own image tag.

## Decisions

- **Repo**: monorepo (one repo, many services). CI builds only changed services via path filters.
- **Database**: one Postgres server, one database + user per service. Azure Database for PostgreSQL Flexible Server on AKS; a single Postgres container locally.
- **Auth**: start with HS256 (shared `JWT_SECRET`); later switch to RS256 where only auth-service holds the private key and publishes the public key at `/.well-known/jwks.json`.
- **Agent routing**: agents-as-tools — the orchestrator is an LLM call whose tools are `delegate_to_todo_agent`, `delegate_to_planner_agent`, …
- **Agent memory**: stored in Postgres (not in process memory), so any replica can serve any request.
- **Kubernetes manifests**: plain YAML + Kustomize (`base/` + `overlays/local`, `overlays/aks`). No Helm for our own services.
- **Monitoring stack**: Helm charts for kube-prometheus-stack, Loki, Alloy (values files in `deploy/monitoring/`, versions pinned). OpenTelemetry + Tempo for traces.

## Steps

- [ ] **1. Monorepo layout + local stack + Next.js**
  - [x] 1a. Move the Go monolith to `services/api/` (temporary name)
  - [x] 1b. Add Postgres to `compose.yaml`
  - [ ] 1c. Scaffold `web/` (Next.js) against the existing `/api/...` endpoints
- [ ] **2. Extract `services/agent` (Python)** — agents-as-tools routing, planner agent, Postgres-backed memory, tools call the API over HTTP
- [ ] **3. Split `services/api` into `services/auth` + `services/todo`** — database per service, shared code to `libs/go/`
- [ ] **4. Local Kubernetes** (kind or k3d) with Kustomize manifests
- [ ] **5. AKS** — ACR, AKS, Azure Postgres, Gateway API + cert-manager, Key Vault for secrets
- [ ] **6. Observability** — Prometheus, Grafana, Loki, Alloy; `/metrics` per service; then Tempo traces
- [ ] **7. CI/CD** — GitHub Actions with path filters, per-service image tags
- [ ] **Later** — RS256/JWKS, Redis, Kafka + notification-service, Argo CD, Linkerd, Helm for our own charts
