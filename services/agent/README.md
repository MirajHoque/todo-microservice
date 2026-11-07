# agent — the AI assistant service (Python / FastAPI)

Being extracted from the Go api in step 2 of `docs/ROADMAP.md`.
It will own the agents (orchestrator, todo agent, planner) and their
memory (`agent_db`), and call the api's HTTP endpoints for todos.

- Language: Python 3.15, FastAPI, managed with [uv](https://docs.astral.sh/uv/)
- Port: **8083**
- Status: 2a — skeleton only (`/health`). Chat still runs in the Go api until 2f.

## Run it

Like every service, it runs natively in its own terminal (see `docs/LOCAL_DEV.md`).

```bash
cd services/agent
cp .env.example .env   # first time only
make install           # first time only — creates .venv/ from uv.lock
make dev               # http://localhost:8083, restarts when you save a file
```

Check: `curl localhost:8083/health` → `{"status":"ok","service":"agent",...}`.
While `ENV=development`, interactive API docs are at http://localhost:8083/docs.

## Commands

| Command | What it does | Go equivalent |
|---|---|---|
| `make install` | Install dependencies into `.venv/` | `go mod download` |
| `make dev` | Run with auto-reload | `make dev` (`go run`) |
| `make test` | Run tests (`pytest`) | `go test ./...` |
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
| `src/agent/routes/` | HTTP handlers |
| `tests/` | Tests, run in-process with FastAPI's TestClient |

## Conventions shared with the other services

- Errors: `{"error": "...", "request_id": "..."}` (same as the Go api).
- `X-Request-ID`: reused from the caller, or generated; returned in the response
  and included in every log line.
- Log fields: `service`, `env`, `request_id`, `user_id`, `method`, `path`,
  `status`, `duration_ms`, `error`, `agent`, `action`.
