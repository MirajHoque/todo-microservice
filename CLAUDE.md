# CLAUDE.md

Guidance for Claude Code (and humans) working in this repo.

## What this repo is

A learning project: the `todo-app` Go monolith (tag `v1-monolith`), now split
into microservices (auth, todo, agent, web), on its way to Azure Kubernetes
Service, one small step at a time.
**Read `docs/ROADMAP.md` first** — it holds the target architecture, the rules
and the current step. Tick off steps there as they are completed.

## How to work here

- The owner is learning Go, agents, Kubernetes and microservices. Explain changes
  in a beginner-friendly way and say *why*, not just what.
- Go step by step: one sub-step per branch/PR, and the app must still run after it.
- Follow the rules in `docs/ROADMAP.md` (no cross-service imports, one owner per table).
- Keep the existing code style: explanatory header comments in each file.

## Layout

- `services/auth/` — Go auth service (port 8081, `auth_db`): register/login/logout, the only one that
  creates JWTs. `make dev`/`make test` (tests use `auth_db_test`, need `make db`)
- `services/todo/` — Go todo service (port 8082, `todo_db`, db user `todo_svc`): todo CRUD; only checks
  JWTs. `make dev`/`make test` (tests use `todo_db_test`, need `make db`)
- `libs/go/` — Go code shared by the Go services (own module): `logger`, `middleware`, `jwtauth`,
  `postgres` (pool + migrations), `respond` (JSON errors), `health`.
  Generic only (ROADMAP rule 4). Services use it via a `replace ../../libs/go` line in `go.mod`;
  check with `cd libs/go && make check && make test`
- `services/agent/` — Python/FastAPI agent service (port 8083): orchestrator + todo + planner agents;
  `uv` + `make dev`/`make test`/`make lint`. Errors and log fields match the Go services.
  Its tools call the todo service (`TODO_URL`) with the user's JWT.
- `web/` — Next.js frontend (port 3000); `web/proxy.ts` forwards `/api/v1/auth/...` to
  `AUTH_URL` (:8081), `/api/v1/todos/...` to `TODO_URL` (:8082) and `/api/v1/agent/...` to `AGENT_URL` (:8083)
- `compose.yaml` — the whole system in containers (`make up` / `make ps` / `make logs` / `make down`): same ports and same Postgres volume as the native run, so only one of the two at a time
- `Makefile` — `make db`, `make psql-auth`/`psql-todo`/`psql-agent`, `make db-stop`, `make svc SERVICE=todo CMD=test`, `make up`/`down`/`ps`/`logs` (compose)
- `docs/` — roadmap and explanations (`docs/LOCAL_DEV.md`: how to run locally)

## Commands

- Build/vet/test a Go service: `cd services/todo && go build ./... && go vet ./... && make test`
  (same in `services/auth`; `make test` needs `make db`)
- Go Docker images are built from the repo root (they need `libs/go`):
  `docker build -f services/todo/Dockerfile -t todo-todo .`
- Run locally: `make db` (Postgres via plain `docker run`), then `make dev` in `services/auth`,
  `services/todo` and `services/agent` (each needs its `.env`, copied from `.env.example`;
  `JWT_SECRET` must be the same in all three).
  The owner runs each service natively, one terminal each, to learn how
  services find each other. Every new service needs its own native run
  path (`make dev` / `npm run dev`, own `.env`, own port) first; then add it to `compose.yaml` as well.
- Web: `cd web && npm run dev` (needs `web/.env.local`, copied from `.env.example`);
  check with `npm run lint && npm run build`. Read `web/AGENTS.md` before
  writing Next.js code — this Next.js version differs from older docs.
- Every API path is under `/api/v1`; through web it is `localhost:3000/api/v1/...`
- Local Postgres: `localhost:5433` (5432 is taken by a Postgres installed on
  the Mac). Container `todo-postgres`, volume `todo-pgdata`. One database + user
  per service, created by `make db` from `db/init.sql`:
  auth → `auth_db` (+ `auth_db_test`) / `auth`,
  todo → `todo_db` (+ `todo_db_test`) / `todo_svc`,
  agent → `agent_db` (+ `agent_db_test`) / `agent`. Users can't connect to
  other services' databases. The `todo` user/database is the server admin and
  its (empty) default database — used only by the root Makefile, never by a service.
- psql shell: `make psql-auth` (auth_db), `make psql-todo` (todo_db), `make psql-agent` (agent_db),
  `make psql` (admin)

## Git

Pushes go to github.com/MirajHoque/todo-microservice over HTTPS with a
personal access token (no SSH key on this machine).
