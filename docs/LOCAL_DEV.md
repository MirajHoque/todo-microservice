# Running locally

We run **each service natively on your Mac, one terminal per service**.
Only Postgres runs in Docker. There is no docker compose in the daily
workflow (yet). That way you see each service start, read its own
config, log on its own and find the others by address — which is what
microservices are about. Compose comes back once all services exist
(see `docs/ROADMAP.md`).

```
Terminal 1:  make db                          # Postgres in Docker  → localhost:5433
Terminal 2:  cd services/auth && make dev     # Go auth service     → localhost:8081
Terminal 3:  cd services/api && make dev      # Go api (todos)      → localhost:8080
Terminal 4:  cd services/agent && make dev    # Python agent        → localhost:8083
Terminal 5:  cd web && npm run dev            # Next.js frontend    → localhost:3000
```

The api will become the todo service (port 8082) in step 3c.
First-time setup for each service is in its own README.

## Why Postgres runs in Docker

Postgres is infrastructure, not a service we write. Running it in Docker
means you don't need it installed on your Mac and everyone gets exactly
the same version (`postgres:18-alpine`).

`make db` is a plain `docker run` (open the root `Makefile` to read it):

| Flag | What it does |
|---|---|
| `--name todo-postgres` | Name the container so we can start/stop it by name |
| `-e POSTGRES_USER/PASSWORD/DB=todo` | On first start, Postgres creates this user and database |
| `-p 5433:5432` | Mac port 5433 → container port 5432 (5432 is taken by the Mac's own Postgres) |
| `-v todo-pgdata:/var/lib/postgresql` | Keep the data in a named volume, so it survives deleting the container |
| `--health-cmd pg_isready ...` | `docker ps` shows `(healthy)` once Postgres accepts connections |
| `postgres:18-alpine` | The ready-made image from Docker Hub — no Dockerfile needed |

The first `make db` creates the container (and downloads the image if
needed). Later runs just `docker start` the existing container.

### One server, one database per service

After Postgres is up, `make db` also runs `db/init.sql` (safe to repeat):

| Service | Database | User | psql shell |
|---|---|---|---|
| api (Go) | `todo` | `todo` | `make psql` |
| auth (Go) | `auth_db` (+ `auth_db_test`) | `auth` | `make psql-auth` |
| agent (Python) | `agent_db` (+ `agent_db_test`) | `agent` | `make psql-agent` |

Each user can only connect to its own database — the agent literally
cannot read the `todos` table, it has to ask the api over HTTP
(ROADMAP rule 3: one owner per table). Nobody but auth can read the
`users` table: the other services know a user only as the `user_id`
inside the JWT. Tables are created by each
service's migrations when it starts, not by `db/init.sql`.

(The `todo` user is a superuser because the Postgres image makes its
first user one — fine locally; step 3 gives the Go services normal users.)

## Running auth and the api

One-time setup:

```bash
cp services/auth/.env.example services/auth/.env   # then set JWT_SECRET (openssl rand -base64 32)
cp services/api/.env.example services/api/.env     # then set the SAME JWT_SECRET
```

`JWT_SECRET` must be the same in auth, the api and the agent: auth
signs the login token with it, the others check the token with it.

Every day:

```bash
make db                          # Terminal 1
cd services/auth && make dev     # Terminal 2 → http://localhost:8081
cd services/api && make dev      # Terminal 3 → http://localhost:8080
```

Check it works:

```bash
curl localhost:8081/health/ready   # auth: "database":{"connected":true}
curl localhost:8080/health/ready   # api:  "database":{"connected":true}
make psql-auth                     # psql shell in auth_db, try \dt
```

Had accounts before step 3b? They were in the api's database. With
auth started once (it creates its `users` table), copy them over:

```bash
make db-copy-users                 # safe to run again
```

You do **not** create tables yourself. Each service runs its own migrations
(SQL files embedded in the binary) every time it starts and skips the ones
already applied.

## Running web (Next.js)

One-time setup:

```bash
cd web
cp .env.example .env.local   # sets AUTH_URL, API_URL and AGENT_URL
npm install                  # downloads dependencies into node_modules/
```

Every day (with Postgres, auth, the api and the agent already running):

```bash
cd web && npm run dev        # Terminal 5 → http://localhost:3000
```

Check the proxy: `curl localhost:3000/api/v1/todos` should return
`{"error":"missing authorization header","request_id":"…"}`. web
forwarded the request to the Go api, and that is the api's answer.
`curl -X POST localhost:3000/api/v1/auth/logout` gets the same error
from the auth service, and
`curl -X DELETE localhost:3000/api/v1/agent/conversation` from the
Python agent. Search each service's terminal for the `request_id` to
see which one answered.

## Stopping and resetting

| Command | Effect |
|---|---|
| `Ctrl+C` in a service terminal | Stop that service |
| `make db-stop` | Stop Postgres, keep the data |
| `make db-reset` | Delete the Postgres container **and all data** (next `make db` starts empty) |

## How the pieces find each other

Every address is configured by hand in each service's env file:

| From → To | Setting | File |
|---|---|---|
| auth → Postgres | `DATABASE_URL=postgres://auth:auth@localhost:5433/auth_db` | `services/auth/.env` |
| api → Postgres | `DATABASE_URL=postgres://todo:todo@localhost:5433/todo` | `services/api/.env` |
| web → auth | `AUTH_URL=http://localhost:8081` (`/api/v1/auth/...`: register, login, logout) | `web/.env.local` |
| agent → Postgres | `DATABASE_URL=postgresql://agent:agent@localhost:5433/agent_db` | `services/agent/.env` |
| web → api | `API_URL=http://localhost:8080` (todos) | `web/.env.local` |
| web → agent | `AGENT_URL=http://localhost:8083` (`/api/v1/agent/...`: chat; logout clears memory) | `web/.env.local` |
| agent → api | `API_URL=http://localhost:8080` (todo tools, with the user's JWT) | `services/agent/.env` |
| agent → LLM | `OPENROUTER_API_KEY`, `AGENT_MODEL` (any model, via OpenRouter) | `services/agent/.env` |

The browser only ever talks to web (`localhost:3000`). web forwards
`/api/v1/auth/...` to `AUTH_URL`, `/api/v1/agent/...` to `AGENT_URL`
and every other `/api/...` to `API_URL` — chosen by path (see
`web/proxy.ts`).

Nobody calls auth to check a login: every service checks the token
itself with the shared `JWT_SECRET`. So the Go services don't know
each other's addresses at all.

If one service is down, the others keep running: stop auth and nobody
can log in, but people who are already logged in keep working (their
token is still valid); stop the agent and the
todo list still works, only the chat says "Cannot reach the agent";
stop the api and the chat can't change todos either (the agent's tools
call the api).

As more services appear, their env files will point at each other the
same way.
