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
```

More terminals are added as services are split out (web, auth, todo, agent).

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

## Stopping and resetting

| Command | Effect |
|---|---|
| `Ctrl+C` in a service terminal | Stop that service |
| `make db-stop` | Stop Postgres, keep the data |
| `make db-reset` | Delete the Postgres container **and all data** (next `make db` starts empty) |

## How the pieces find each other

Every address is configured by hand in each service's `.env`:

- api → Postgres: `DATABASE_URL=postgres://todo:todo@localhost:5433/todo`

As more services appear, their `.env` files will point at each other the
same way (e.g. web → api at `http://localhost:8080`).
