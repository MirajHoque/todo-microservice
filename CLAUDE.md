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
- `compose.yaml` — runs all services locally; each reads `services/<name>/.env`
- `Makefile` — `make up`, `make down`, `make svc SERVICE=api CMD=test`
- `docs/` — roadmap and explanations

## Commands

- Build/vet the api: `cd services/api && go build ./... && go vet ./...`
- Run everything: `make up` (needs `services/api/.env`, copied from `.env.example`)
- API is served under `/api/v1` on `localhost:8080`
- Local Postgres: `localhost:5433` from the Mac (5432 is taken by a Postgres
  installed on the Mac), `postgres:5432` from inside compose. User/password/db: `todo`
- psql shell: `docker exec -it todo-postgres psql -U todo -d todo`

## Git

Pushes go to github.com/MirajHoque/todo-microservice over HTTPS with a
personal access token (no SSH key on this machine).
