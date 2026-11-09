# agent — the AI assistant service (Python / FastAPI)

Being extracted from the Go api in step 2 of `docs/ROADMAP.md`.
It will own the agents (orchestrator, todo agent, planner) and their
memory (`agent_db`), and call the api's HTTP endpoints for todos.

- Language: Python 3.15, FastAPI, managed with [uv](https://docs.astral.sh/uv/)
- Port: **8083**
- Status: 2d — health checks, own database, JWT auth, conversation endpoints,
  client for the api's todo endpoints.
  Chat still runs in the Go api until 2f.

## Run it

Like every service, it runs natively in its own terminal (see `docs/LOCAL_DEV.md`).
Start Postgres first (`make db` in the repo root) — it also creates this
service's user and databases.

```bash
cd services/agent
cp .env.example .env   # first time only — then set JWT_SECRET (see "Auth" below)
make install           # first time only — creates .venv/ from uv.lock
make dev               # http://localhost:8083, restarts when you save a file
```

Check:
- `curl localhost:8083/health` → `{"status":"ok","service":"agent",...}` (process is up)
- `curl localhost:8083/health/ready` → `"status":"ready"` (database reachable; 503 if not)

While `ENV=development`, interactive API docs are at http://localhost:8083/docs.

## Endpoints

| Method + path | Auth | What it does |
|---|---|---|
| `GET /health` | — | Liveness: the process is up |
| `GET /health/ready` | — | Readiness: the database answers (503 if not) |
| `GET /api/v1/agent/conversation` | JWT | Your saved chat messages, oldest first |
| `DELETE /api/v1/agent/conversation` | JWT | Forget your conversation (204) |

`POST /api/v1/agent/chat` arrives in step 2e.

## Calling the api (todos)

The `todos` table belongs to the api service; this service can't even
connect to that database. Its tools change todos through the api's HTTP
endpoints, via `src/agent/todo_client.py` (`API_URL`, default
`http://localhost:8080`):

| Header sent | Why |
|---|---|
| `Authorization: Bearer <the user's JWT>` | The agent acts **as the user**, with no extra power — the api checks ownership exactly as for web, so even a tricked LLM can only touch this user's todos |
| `X-Request-ID: <same id>` | One chat message can be followed through both services' logs |

Api errors come back as `TodoAPIError(status, message)` with the api's own
message ("todo not found", …); api down → 503, too slow → 504.

## Auth

This service has no users and never sees passwords. The api issues a JWT
at login; this service only **verifies** it (`src/agent/auth.py`):
signature (shared `JWT_SECRET`), algorithm HS256 only, not expired,
issuer `todo-app`, and reads `user_id` from it. Errors match the Go api:
`missing authorization header`, `authorization header must be: Bearer <token>`,
`token is invalid`, `token has expired` (all 401).

`JWT_SECRET` in `.env` **must be the same value** as in `services/api/.env`,
and at least 32 characters — otherwise the service refuses to start. Copy it
without printing it:

```bash
grep '^JWT_SECRET=' ../api/.env >> .env   # then delete the placeholder line
```

(Later, in the RS256 step, only the auth service will hold a private key
and this service will need just the public key.)

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
service. The id comes from the caller's verified JWT — never from the URL
or body — so a user can only reach their own conversation.

To change the schema, **add** a new file (`003_...sql`) — never edit one
that has already run.

## Commands

| Command | What it does | Go equivalent |
|---|---|---|
| `make install` | Install dependencies into `.venv/` | `go mod download` |
| `make dev` | Run with auto-reload | `make dev` (`go run`) |
| `make test` | Run tests (`pytest`; DB tests need `make db`, real-api tests need the api running — else skipped) | `go test ./...` |
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
| `src/agent/auth.py` | JWT check; `CurrentUser` dependency → the caller's user id |
| `src/agent/memory.py` | SQL for conversations/messages (read, clear) |
| `src/agent/todo_client.py` | HTTP client for the api's todo endpoints, as the user |
| `src/agent/migrate.py` | Applies `migrations/*.sql` at startup |
| `src/agent/migrations/` | Numbered SQL files (the schema, step by step) |
| `src/agent/routes/` | HTTP handlers: `health.py`, `conversation.py` |
| `tests/conftest.py` | Shared test setup: uses `agent_db_test` + a test JWT secret; skips DB tests if Postgres is down |
| `tests/helpers.py` | `make_token()` / `auth()` to build good and bad tokens in tests |
| `tests/` | Tests, run in-process with FastAPI's TestClient |

## Conventions shared with the other services

- Errors: `{"error": "...", "request_id": "..."}` (same as the Go api).
- `X-Request-ID`: reused from the caller, or generated; returned in the response
  and included in every log line.
- Log fields: `service`, `env`, `request_id`, `user_id`, `method`, `path`,
  `status`, `duration_ms`, `error`, `agent`, `action`.
