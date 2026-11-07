# agent — the AI assistant service (Python / FastAPI)

Being extracted from the Go api in step 2 of `docs/ROADMAP.md`.
It will own the agents (orchestrator, todo agent, planner) and their
memory (`agent_db`), and call the api's HTTP endpoints for todos.

- Language: Python 3.15, FastAPI, managed with [uv](https://docs.astral.sh/uv/)
- Port: **8083**
- Status: 2b — health checks + its own database. Chat still runs in the Go api until 2f.

## Run it

Like every service, it runs natively in its own terminal (see `docs/LOCAL_DEV.md`).
Start Postgres first (`make db` in the repo root) — it also creates this
service's user and databases.

```bash
cd services/agent
cp .env.example .env   # first time only
make install           # first time only — creates .venv/ from uv.lock
make dev               # http://localhost:8083, restarts when you save a file
```

Check:
- `curl localhost:8083/health` → `{"status":"ok","service":"agent",...}` (process is up)
- `curl localhost:8083/health/ready` → `"status":"ready"` (database reachable; 503 if not)

While `ENV=development`, interactive API docs are at http://localhost:8083/docs.

## Its database

| | |
|---|---|
| Database | `agent_db` (tests use `agent_db_test`) |
| User | `agent` / `agent` — can't connect to any other service's database |
| Created by | `make db` / `make db-init` in the repo root (`db/init.sql`) |
| Tables | `conversations` (one per user), `messages` (full content blocks as JSONB, tool calls included) |
| Schema changes | SQL files in `src/agent/migrations/`, applied automatically at startup |
| psql shell | `make psql-agent` (repo root) |

`user_id` in `conversations` has no foreign key: users belong to another
service. The id comes from the user's JWT (step 2c).

To change the schema, **add** a new file (`003_...sql`) — never edit one
that has already run.

## Commands

| Command | What it does | Go equivalent |
|---|---|---|
| `make install` | Install dependencies into `.venv/` | `go mod download` |
| `make dev` | Run with auto-reload | `make dev` (`go run`) |
| `make test` | Run tests (`pytest`; database tests need `make db`, else skipped) | `go test ./...` |
| `make lint` | Lint + format check (`ruff`) | `go vet` + `gofmt -l` |
| `make fmt` | Fix formatting | `gofmt -w` |

## Layout

| Path | What it is |
|---|---|
| `pyproject.toml` | Project + dependencies (like `go.mod`) |
| `uv.lock` | Exact versions (like `go.sum`) |
| `.python-version` | Python version uv uses |
| `src/agent/__main__.py` | Entry point: `python -m agent` starts the server |
| `src/agent/main.py` | Builds the app: middleware (request ID, logging), error shape, routes |
| `src/agent/config.py` | Settings from env / `.env` |
| `src/agent/log.py` | JSON logs with the same field names as the Go api |
| `src/agent/db.py` | Database connection pool; `Pool` dependency for routes |
| `src/agent/migrate.py` | Applies `migrations/*.sql` at startup |
| `src/agent/migrations/` | Numbered SQL files (the schema, step by step) |
| `src/agent/routes/` | HTTP handlers (`health.py`: `/health`, `/health/ready`) |
| `tests/conftest.py` | Shared test setup: uses `agent_db_test`, skips DB tests if Postgres is down |
| `tests/` | Tests, run in-process with FastAPI's TestClient |

## Conventions shared with the other services

- Errors: `{"error": "...", "request_id": "..."}` (same as the Go api).
- `X-Request-ID`: reused from the caller, or generated; returned in the response
  and included in every log line.
- Log fields: `service`, `env`, `request_id`, `user_id`, `method`, `path`,
  `status`, `duration_ms`, `error`, `agent`, `action`.
