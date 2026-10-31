# Running locally

There are two ways to run the system on your laptop. Use **mode 1** day to day.

| | Mode 1: services on your Mac (default) | Mode 2: everything in Docker |
|---|---|---|
| Postgres | Docker container | Docker container |
| Services | Run natively, one terminal each | Containers built by compose |
| Start | `make db`, then `make dev` per service | `make up` |
| Good for | Writing code, reading logs, learning how services find each other | Checking that the whole system works together before a PR |

Why the database is in Docker even in mode 1: you don't need Postgres installed
on your Mac, and everyone gets exactly the same version (`postgres:18-alpine`).
Only infrastructure (databases, later Redis/Kafka) lives in Docker by default;
the services we write run natively so you see them start, log and fail.

## Mode 1: services on your Mac

One-time setup:

```bash
cp services/api/.env.example services/api/.env   # then set JWT_SECRET and OPENROUTER_API_KEY
```

Every day:

```bash
make db                          # Terminal 1: start Postgres, waits until healthy
cd services/api && make dev      # Terminal 2: run the api on http://localhost:8080
```

Check it works:

```bash
curl localhost:8080/health/ready   # "database":{"connected":true}
make psql                          # psql shell, try \dt
```

You do **not** create tables yourself. Each service runs its own migrations
(SQL files embedded in the binary) every time it starts and skips the ones
already applied.

Stop: `Ctrl+C` the service, then `make db-stop` (your data is kept).

### How the pieces find each other

- The Postgres container creates the `todo` user and database on its first
  start, from `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` in
  `compose.yaml`.
- It is published on **localhost:5433** (5432 is taken by the Postgres
  installed on the Mac). `services/api/.env` points at that address.

## Mode 2: everything in Docker

```bash
make up      # builds images, starts Postgres, then the api once Postgres is healthy
make logs    # tail logs
make down    # stop (add -v via `docker compose down -v` to wipe the database)
```

Inside the compose network services reach each other by service name, so
`compose.yaml` overrides `DATABASE_URL` to use `postgres:5432` instead of the
`localhost:5433` in `.env`.

Don't run both modes at once: the native api and the api container both want
port 8080.
