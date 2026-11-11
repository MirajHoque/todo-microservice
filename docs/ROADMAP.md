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

- [x] **1. Monorepo layout + local stack + Next.js**
  - [x] 1a. Move the Go monolith to `services/api/` (temporary name)
  - [x] 1b. Add Postgres to `compose.yaml` (later replaced by `make db`, a plain `docker run`; compose is parked)
  - [x] 1c. `web/` (Next.js): login/register, todos, AI chat against the existing `/api/v1` endpoints. Runs natively with `npm run dev`; `/api` is forwarded by `proxy.ts` (`API_URL` read at runtime); Dockerfile with standalone output. The old Go HTML pages (`services/api/web/`) still exist — remove them in step 3.
- [x] **2. Extract `services/agent` (Python)** — agents-as-tools routing, planner agent, Postgres-backed memory, tools call the API over HTTP. Memory must store full turns *including tool calls and results* — the Go agent stores only text, so on later turns the model thinks it never called its tools (seen in 1c.6)
  - [x] 2a. Scaffold: FastAPI + uv on port 8083, health endpoints, JSON logs and errors shaped like the Go api's
  - [x] 2b. Own database `agent_db` (own user, can't reach `todo`), migrations at startup, conversations/messages tables
  - [x] 2c. Verify the api's JWTs (shared HS256 secret); `GET`/`DELETE /api/v1/agent/conversation`
  - [x] 2d. `TodoClient`: todo changes go through the api's HTTP endpoints, as the user (JWT + `X-Request-ID` forwarded)
  - [x] 2e. Todo agent via the OpenRouter SDK (any model/provider); full messages incl. tool calls stored append-only (fixes 1c.6)
  - [x] 2f. web routes `/api/v1/agent/*` to `AGENT_URL`; logout clears the agent's memory; Go agent code and `OPENROUTER_API_KEY` removed from the api
  - [x] 2g. Orchestrator with the todo agent and a read-only planner agent as tools; one step budget for all agents
  - [x] 2h. Dockerfile (uv, no dev deps, non-root, healthcheck); docs
  - [x] 2i. Guardrails — 2i.1 deleting needs the user's Confirm click (human-in-the-loop); 2i.2 per-user rate limit + daily cost cap; 2i.3 prompt-injection hardening, stay on topic, per-agent token caps
- [ ] **3. Split `services/api` into `services/auth` + `services/todo`** — database per service, shared code to `libs/go/`
- [ ] **3½. Compose for the whole system** — bring `compose.yaml` back (it is parked until now) so every service plus Postgres starts with one command. Until this step each service runs natively in its own terminal (see `docs/LOCAL_DEV.md`).
- [ ] **4. Local Kubernetes** (kind or k3d) with Kustomize manifests
- [ ] **5. AKS** — ACR, AKS, Azure Postgres, Gateway API + cert-manager, Key Vault for secrets
- [ ] **6. Observability** — Prometheus, Grafana, Loki, Alloy; `/metrics` per service; then Tempo traces
- [ ] **7. CI/CD** — GitHub Actions with path filters, per-service image tags
- [ ] **Later** — RS256/JWKS, Redis, Kafka + notification-service, Argo CD, Linkerd, Helm for our own charts
