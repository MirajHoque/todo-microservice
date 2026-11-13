# auth — accounts and tokens

The auth service of the todo system (see `docs/ROADMAP.md`). Split out
of the Go monolith in step 3b.

- Language: Go · Port: **8081** · Database: **`auth_db`** (user `auth`)
- Owns: the `users` table — nobody else can read it
- It is the **only** service that creates JWTs

## What it does

| Endpoint | Needs a token? | What it does |
|---|---|---|
| `POST /api/v1/auth/register` | no | Creates an account, returns `{token, user}` |
| `POST /api/v1/auth/login` | no | Checks email + password, returns `{token, user}` |
| `POST /api/v1/auth/logout` | yes | Only logs it — a JWT can't be "switched off"; the browser deletes it |
| `GET /health` | no | Is the process alive? |
| `GET /health/ready` | no | Can it reach its database? |

Errors look the same as in every other service:
`{"error": "...", "request_id": "..."}`.

## How the other services know who you are

They never ask this service. They only check the token:

```
1. browser ── email + password ──▶ auth ── checks the password hash in auth_db
2. browser ◀── token (JWT) ─────── auth    signs {"user_id": "…", "exp": …} with JWT_SECRET
3. browser ── token ──▶ todo / agent       check the signature with the SAME JWT_SECRET
                                           and read user_id — no call to auth, no users table
```

That is why `JWT_SECRET` must be identical in `services/auth/.env`,
`services/todo/.env` and `services/agent/.env`. If one differs, that
service answers `401 token is invalid` for every request.

Trade-off to know about: because nobody asks auth, a token stays valid
until it expires (`JWT_EXPIRY`, 24h), even after logout. The roadmap's
"Later" list has RS256/JWKS, where only auth holds the signing key.

## Passwords

Stored only as a **bcrypt hash** (`BCRYPT_COST`, default 12 — each
+1 doubles the work to guess a password). The hash is never sent in a
response. A wrong password and an unknown email give the same answer
(`invalid email or password`), so nobody can find out which emails
have an account. Emails are lower-cased and trimmed at register and
login.

## Run it

One-time setup:

```bash
make db                                   # in the repo root: creates auth_db + user auth
cd services/auth
cp .env.example .env                      # then set JWT_SECRET to the SAME value as services/todo/.env
```

Every day:

```bash
cd services/auth && make dev              # → http://localhost:8081
```

Check it works:

```bash
curl localhost:8081/health/ready          # "database":{"connected":true}
make psql-auth                            # (repo root) psql shell in auth_db, try: \dt
```

The `users` table is created by this service's own migration
(`migrations/001_create_users.sql`, embedded in the binary) when it
starts.

## Commands

| Command | What it does |
|---|---|
| `make dev` | Run with `go run` (reads `.env`) |
| `make test` | Tests, against the real database `auth_db_test` (needs `make db`; skipped without it) |
| `make build` / `make run` | Compile to `./bin/auth` / compile and run |
| `make docker` | Build the image `todo-auth` (from the repo root — it needs `libs/go`) |

Run the image against your local Postgres:

```bash
docker run --rm -p 8081:8081 --env-file services/auth/.env \
  -e DATABASE_URL='postgres://auth:auth@host.docker.internal:5433/auth_db?sslmode=disable' todo-auth
```

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8081` | Port to listen on |
| `ENV` | `development` | `development` or `production` |
| `DATABASE_URL` | — (required) | This service's own database |
| `JWT_SECRET` | — (required, ≥ 32 chars) | Signs the tokens; same value in every service |
| `JWT_EXPIRY` | `24h` | How long a token is valid |
| `BCRYPT_COST` | `12` | How slow password hashing is (10–31) |
| `LOG_LEVEL`, `LOG_FORMAT` | `info`, `json` | Logging |

## Layout

| Path | What it is |
|---|---|
| `cmd/server/main.go` | Start-up: config → logger → database → migrations → router → HTTP server |
| `internal/config/` | Reads the environment variables |
| `internal/auth/jwt.go` | **Creates** tokens (checking them is shared: `libs/go/jwtauth`) |
| `internal/db/user_repository.go` | All SQL for the `users` table |
| `internal/models/` | `User` and the request/response bodies |
| `internal/handlers/` | `routes.go` (URL map), `auth_handler.go` (register, login, logout), tests |
| `migrations/` | SQL files, run at start-up |

Generic code — logger, middleware, database pool, migration runner,
health endpoints, JSON errors, JWT check — is not here: it comes from
the shared library `libs/go` (see its README).
