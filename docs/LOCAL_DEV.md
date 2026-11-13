# Running locally

There are two ways to run the system. Use one at a time — they use the
same ports and the same data.

1. **Natively, one terminal per service** (this page, the day-to-day
   way). Only Postgres runs in Docker. You see each service start, read
   its own config, log on its own and find the others by address —
   which is what microservices are about. Code changes show up at once.
2. **Everything in containers with one command**: `make up`
   (see [Everything in containers](#everything-in-containers-make-up)
   at the end). Good for a quick "does the whole thing work?" and for
   testing the Docker images before Kubernetes.

```
Terminal 1:  make db                          # Postgres in Docker  → localhost:5433
Terminal 2:  cd services/auth && make dev     # Go auth service     → localhost:8081
Terminal 3:  cd services/todo && make dev     # Go todo service     → localhost:8082
Terminal 4:  cd services/agent && make dev    # Python agent        → localhost:8083
Terminal 5:  cd web && npm run dev            # Next.js frontend    → localhost:3000
```

First-time setup for each service is in its own README.

## Why Postgres runs in Docker

Postgres is infrastructure, not a service we write. Running it in Docker
means you don't need it installed on your Mac and everyone gets exactly
the same version (`postgres:18-alpine`).

`make db` is a plain `docker run` (open the root `Makefile` to read it):

| Flag | What it does |
|---|---|
| `--name todo-postgres` | Name the container so we can start/stop it by name |
| `-e POSTGRES_USER/PASSWORD/DB=todo` | On first start, Postgres creates this (admin) user and database |
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
| auth (Go) | `auth_db` (+ `auth_db_test`) | `auth` | `make psql-auth` |
| todo (Go) | `todo_db` (+ `todo_db_test`) | `todo_svc` | `make psql-todo` |
| agent (Python) | `agent_db` (+ `agent_db_test`) | `agent` | `make psql-agent` |

Each user can only connect to its own database — the agent literally
cannot read the `todos` table, it has to ask the todo service over HTTP
(ROADMAP rule 3: one owner per table). Nobody but auth can read the
`users` table: the other services know a user only as the `user_id`
inside the JWT. Tables are created by each service's migrations when
it starts, not by `db/init.sql`. The `_test` databases are for each
service's tests, so tests never touch your real data.

There is also a database called `todo` with a user `todo`. That is the
server's **admin** user and its default database (the Postgres image
creates them from the `POSTGRES_*` variables) — which is why the todo
service's own user is called `todo_svc`. The admin can see every
database; only the root `Makefile` uses it, to create the per-service
users and databases. No service logs in with it, and its `todo`
database is empty (it was the monolith's database until step 3).
`make psql` opens a shell as the admin: `\l` lists the databases,
`\c auth_db` switches to one.

## Running auth and todo

One-time setup:

```bash
cp services/auth/.env.example services/auth/.env   # then set JWT_SECRET (openssl rand -base64 32)
cp services/todo/.env.example services/todo/.env   # then set the SAME JWT_SECRET
```

`JWT_SECRET` must be the same in auth, todo and the agent: auth signs
the login token with it, the others check the token with it.

Every day:

```bash
make db                          # Terminal 1
cd services/auth && make dev     # Terminal 2 → http://localhost:8081
cd services/todo && make dev     # Terminal 3 → http://localhost:8082
```

Check it works:

```bash
curl localhost:8081/health/ready   # auth: "database":{"connected":true}
curl localhost:8082/health/ready   # todo: "database":{"connected":true}
make psql-auth                     # psql shell in auth_db, try \dt
make psql-todo                     # psql shell in todo_db
```

You do **not** create tables yourself. Each service runs its own migrations
(SQL files embedded in the binary) every time it starts and skips the ones
already applied.

## Running web (Next.js)

One-time setup:

```bash
cd web
cp .env.example .env.local   # sets AUTH_URL, TODO_URL and AGENT_URL
npm install                  # downloads dependencies into node_modules/
```

Every day (with Postgres, auth, todo and the agent already running):

```bash
cd web && npm run dev        # Terminal 5 → http://localhost:3000
```

Check the proxy: `curl localhost:3000/api/v1/todos` should return
`{"error":"missing authorization header","request_id":"…"}`. web
forwarded the request to the todo service, and that is its answer.
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
| todo → Postgres | `DATABASE_URL=postgres://todo_svc:todo_svc@localhost:5433/todo_db` | `services/todo/.env` |
| agent → Postgres | `DATABASE_URL=postgresql://agent:agent@localhost:5433/agent_db` | `services/agent/.env` |
| web → auth | `AUTH_URL=http://localhost:8081` (`/api/v1/auth/...`: register, login, logout) | `web/.env.local` |
| web → todo | `TODO_URL=http://localhost:8082` (`/api/v1/todos/...`) | `web/.env.local` |
| web → agent | `AGENT_URL=http://localhost:8083` (`/api/v1/agent/...`: chat; logout clears memory) | `web/.env.local` |
| agent → todo | `TODO_URL=http://localhost:8082` (todo tools, with the user's JWT) | `services/agent/.env` |
| agent → LLM | `OPENROUTER_API_KEY`, `AGENT_MODEL` (any model, via OpenRouter) | `services/agent/.env` |

The browser only ever talks to web (`localhost:3000`). web forwards
`/api/v1/auth/...` to `AUTH_URL`, `/api/v1/todos/...` to `TODO_URL`
and `/api/v1/agent/...` to `AGENT_URL` — chosen by path (see
`web/proxy.ts`). Any other `/api/...` path gets a 404 from web itself.

Nobody calls auth to check a login: every service checks the token
itself with the shared `JWT_SECRET`. So auth and todo don't know each
other's addresses at all. The only service-to-service call is
agent → todo.

If one service is down, the others keep running:

- stop **auth**: nobody can log in, but people who are already logged
  in keep working (their token is still valid)
- stop the **agent**: the todo list still works, only the chat says
  "Cannot reach the agent"
- stop **todo**: login still works, but the list can't load and the
  chat can't change todos either (the agent's tools call the todo
  service)

## Everything in containers (`make up`)

`compose.yaml` describes the same five pieces as containers: Postgres,
auth, todo, agent and web. One command builds the images (from the
same Dockerfiles Kubernetes will use in step 4) and starts them:

```bash
# first stop the native terminals (Ctrl+C) — the ports are the same
make up        # build + start everything, waits until all are healthy
make ps        # what is running?
make logs      # follow all logs   (one service: make logs SERVICE=auth)
make down      # stop and remove the containers — your data is kept
```

Then open http://localhost:3000 as usual. To go back to the native
way: `make down`, then `make db` and `make dev` in each service.

What is the same as the native run:

- **The ports**: 3000, 8081, 8082, 8083 and 5433. That is why only one
  way can run at a time ("port is already allocated" means something
  native is still running).
- **The data**: compose's Postgres uses the same volume (`todo-pgdata`)
  as `make db`, so your accounts and todos are there in both. Two
  Postgres servers must never use one data folder at the same time, so
  `make up` stops the `make db` container first.
- **The secrets**: each container reads its service's own `.env`
  (`services/auth/.env`, …). They must exist, with the same
  `JWT_SECRET` in all three — exactly as for the native run.

What is different — **the addresses**. Inside a container `localhost`
is the container itself, not your Mac. Compose puts all containers on
one private network where each service's name is a hostname, and
`compose.yaml` replaces the `localhost` addresses from the `.env` files:

| From → To | Native | In compose |
|---|---|---|
| auth / todo / agent → Postgres | `localhost:5433` | `postgres:5432` |
| web → auth | `http://localhost:8081` | `http://auth:8081` |
| web → todo | `http://localhost:8082` | `http://todo:8082` |
| web → agent | `http://localhost:8083` | `http://agent:8083` |
| agent → todo | `http://localhost:8082` | `http://todo:8082` |

Kubernetes works the same way: there the name will be a `Service`.

Good to know:

- After changing code, run `make up` again: it rebuilds only the
  images whose files changed and restarts those containers.
- Try stopping one piece, as in the list above:
  `docker compose stop auth`, then `docker compose start auth`.
- The Postgres container is called `todo-postgres-1` here (the
  `make db` one is `todo-postgres`), so for a psql shell use
  `make psql-auth DB_CONTAINER=todo-postgres-1` (same for the other
  `psql` targets).
- On a brand-new machine `make up` alone is enough for the database:
  on an empty volume Postgres runs `db/init.sql` itself.
