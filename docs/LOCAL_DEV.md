# Running locally

We run **each service natively on your Mac, one terminal per service**.
Only Postgres runs in Docker. There is no docker compose in the daily
workflow (yet). That way you see each service start, read its own
config, log on its own and find the others by address — which is what
microservices are about. Compose comes back once all services exist
(see `docs/ROADMAP.md`).

```
Terminal 1:  make db                          # Postgres in Docker  → localhost:5433
Terminal 2:  cd services/api && make dev      # Go api              → localhost:8080
Terminal 3:  cd web && npm run dev            # Next.js frontend    → localhost:3000
```

More terminals are added as services are split out (auth, todo, agent).

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

## Running the api

One-time setup:

```bash
cp services/api/.env.example services/api/.env   # then set JWT_SECRET and OPENROUTER_API_KEY
```

Every day:

```bash
make db                          # Terminal 1
cd services/api && make dev      # Terminal 2 → http://localhost:8080
```

Check it works:

```bash
curl localhost:8080/health/ready   # "database":{"connected":true}
make psql                          # psql shell, try \dt
```

You do **not** create tables yourself. Each service runs its own migrations
(SQL files embedded in the binary) every time it starts and skips the ones
already applied.

## Running web (Next.js)

One-time setup:

```bash
cd web
cp .env.example .env.local   # sets API_URL=http://localhost:8080
npm install                  # downloads dependencies into node_modules/
```

Every day (with Postgres and the api already running):

```bash
cd web && npm run dev        # Terminal 3 → http://localhost:3000
```

Check the proxy: `curl localhost:3000/api/v1/todos` should return
`{"error":"missing authorization header"}`. web forwarded the request
to the Go api, and that is the api's answer.

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
| api → Postgres | `DATABASE_URL=postgres://todo:todo@localhost:5433/todo` | `services/api/.env` |
| web → api | `API_URL=http://localhost:8080` | `web/.env.local` |

The browser only ever talks to web (`localhost:3000`). web forwards
`/api/...` to `API_URL` (see `web/proxy.ts`).

If one service is down, the others keep running: stop the api and web's
pages still load, only its `/api/...` calls fail (HTTP 500).

As more services appear, their env files will point at each other the
same way.
