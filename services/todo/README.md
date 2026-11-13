# todo — the todos

The todo service of the todo system (see `docs/ROADMAP.md`). It is what
was left of the Go monolith after auth (step 3b) and the agent (step 2)
moved out; in step 3c it got its own name, port and database.

- Language: Go · Port: **8082** · Database: **`todo_db`** (user `todo_svc`)
- Owns: the `todos` table — nobody else can read it
- Has **no users and no login**: it only checks the token auth created

## What it does

Every todo endpoint needs `Authorization: Bearer <token>`.

| Endpoint | What it does |
|---|---|
| `GET /api/v1/todos` | My todos, newest first (`[]` when there are none) |
| `POST /api/v1/todos` | Create: `{"title": "...", "priority": "low\|medium\|high", "description": "..."}` → 201 |
| `PATCH /api/v1/todos/{id}` | Change only the fields you send, e.g. `{"done": true}` |
| `DELETE /api/v1/todos/{id}` | Delete → 204 |
| `GET /health`, `GET /health/ready` | Alive? / can it reach its database? (no token) |

Errors look the same as in every other service:
`{"error": "...", "request_id": "..."}`.

| Status | When |
|---|---|
| 400 | Broken JSON, empty title, title over 255 characters, unknown priority |
| 401 | No token, bad token, expired token |
| 404 | The todo doesn't exist — **or belongs to someone else** |

## Who calls it

```
browser ──▶ web (proxy.ts: /api/v1/todos → TODO_URL) ──▶ todo
agent   ──▶ todo            (its tools, with the user's own token)
```

Both use the same endpoints and get the same rules. The agent has no
special access: it acts as the user, so even a confused LLM can only
touch that user's todos.

## How it knows whose todos they are

The user's id comes from the **token**, never from the request:

1. The shared JWT check (`libs/go/jwtauth`) verifies the signature with
   `JWT_SECRET` — the same value the auth service signed it with.
2. It puts `user_id` into the request context.
3. Every SQL query has `WHERE ... AND user_id = $n`.

So a `user_id` in the request body is ignored, and someone else's todo
answers 404, exactly like a todo that doesn't exist (a 403 would
confirm the id is real).

This service never calls auth and has no `users` table. That also
means the `todos.user_id` column has **no foreign key**: the users
live in another database. Trade-off: deleting an account doesn't delete
its todos automatically — auth will have to tell this service (an
event; see Kafka under "Later" in the roadmap).

## Run it

One-time setup:

```bash
make db                                   # in the repo root: creates todo_db + user todo_svc
cd services/todo
cp .env.example .env                      # then set JWT_SECRET to the SAME value as services/auth/.env
```

Every day:

```bash
cd services/todo && make dev              # → http://localhost:8082
```

Check it works:

```bash
curl localhost:8082/health/ready          # "database":{"connected":true}
make psql-todo                            # (repo root) psql shell in todo_db, try: \dt
```

The `todos` table is created by this service's own migration
(`migrations/001_create_todos.sql`, embedded in the binary) when it
starts.

## Commands

| Command | What it does |
|---|---|
| `make dev` | Run with `go run` (reads `.env`) |
| `make test` | Tests, against the real database `todo_db_test` (needs `make db`; skipped without it) |
| `make build` / `make run` | Compile to `./bin/todo` / compile and run |
| `make docker` | Build the image `todo-todo` (from the repo root — it needs `libs/go`) |

The tests need no auth service: a test signs its own token with a test
secret, the same way auth would.

Run the image against your local Postgres:

```bash
docker run --rm -p 8082:8082 --env-file services/todo/.env \
  -e DATABASE_URL='postgres://todo_svc:todo_svc@host.docker.internal:5433/todo_db?sslmode=disable' todo-todo
```

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8082` | Port to listen on |
| `ENV` | `development` | `development` or `production` |
| `DATABASE_URL` | — (required) | This service's own database |
| `JWT_SECRET` | — (required, ≥ 32 chars) | Checks the tokens; same value as in auth |
| `LOG_LEVEL`, `LOG_FORMAT` | `info`, `json` | Logging |

## Layout

| Path | What it is |
|---|---|
| `cmd/server/main.go` | Start-up: config → logger → database → migrations → router → HTTP server |
| `internal/config/` | Reads the environment variables |
| `internal/db/todo_repository.go` | All SQL for the `todos` table |
| `internal/models/` | `Todo`, its rules (`Validate`), and the request bodies |
| `internal/handlers/` | `routes.go` (URL map), `todo_handler.go` (create, list, update, delete), tests |
| `migrations/` | SQL files, run at start-up |

Generic code — logger, middleware, database pool, migration runner,
health endpoints, JSON errors, JWT check — is not here: it comes from
the shared library `libs/go` (see its README).
