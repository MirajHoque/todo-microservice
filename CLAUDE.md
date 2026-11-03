# CLAUDE.md

Guidance for Claude Code (and humans) working in this repo.

## What this repo is

A learning project: the `todo-app` Go monolith (tag `v1-monolith`) being turned
into microservices on Azure Kubernetes Service, one small step at a time.
**Read `docs/ROADMAP.md` first** — it holds the target architecture, the rules
and the current step. Tick off steps there as they are completed.

## How to work here

- The owner is learning Go, agents, Kubernetes and microservices. Explain changes
  in a beginner-friendly way and say *why*, not just what.
- Go step by step: one sub-step per branch/PR, and the app must still run after it.
- Follow the rules in `docs/ROADMAP.md` (no cross-service imports, one owner per table).
- Keep the existing code style: explanatory header comments in each file.

## Layout

- `services/api/` — the Go monolith (temporary; will be split into `auth` and `todo`)
- `web/` — Next.js frontend (port 3000); forwards `/api/...` to `API_URL` via `web/proxy.ts`
- `compose.yaml` — **parked**: not used or updated until all services exist (see ROADMAP)
- `Makefile` — `make db`, `make psql`, `make db-stop`, `make svc SERVICE=api CMD=test`
- `docs/` — roadmap and explanations (`docs/LOCAL_DEV.md`: how to run locally)

## Commands

- Build/vet the api: `cd services/api && go build ./... && go vet ./...`
- Run locally: `make db` (Postgres via plain `docker run`), then
  `cd services/api && make dev` (needs `services/api/.env`, copied from `.env.example`).
  The owner runs each service natively, one terminal each, to learn how
  services find each other. Every new service needs its own native run
  path (`make dev` / `npm run dev`, own `.env`, own port) — don't add it to compose.
- Web: `cd web && npm run dev` (needs `web/.env.local`, copied from `.env.example`);
  check with `npm run lint && npm run build`. Read `web/AGENTS.md` before
  writing Next.js code — this Next.js version differs from older docs.
- API is served under `/api/v1` on `localhost:8080`
- Local Postgres: `localhost:5433` (5432 is taken by a Postgres installed on
  the Mac). Container `todo-postgres`, volume `todo-pgdata`. User/password/db: `todo`
- psql shell: `make psql`

## Git

Pushes go to github.com/MirajHoque/todo-microservice over HTTPS with a
personal access token (no SSH key on this machine).
