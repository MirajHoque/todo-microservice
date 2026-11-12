# libs/go — code shared by the Go services

A small Go library (its own module, its own `go.mod`). It is **not** a
service: no `main.go`, no port, no `.env`. Services import it.

| Package | What it does |
|---|---|
| `logger` | JSON logs with the same field names in every service (`service`, `request_id`, `user_id`, …) |
| `middleware` | HTTP middleware: request id, per-request logger, access log, panic recovery, user id in the request context |
| `jwtauth` | **Checks** JWTs (`Verifier`) and protects routes (`Verifier.Middleware`) |
| `respond` | JSON responses; the error shape `{"error", "request_id"}` every service uses |
| `postgres` | Connection pool (`Connect`) and the migration runner (`Migrate`) — no SQL about any table |
| `health` | The two health endpoints: `GET /health` and `GET /health/ready` |

## The rule: generic only

Code belongs here only if **every** service could use it and it knows
nothing about users or todos (ROADMAP rule 4). A quick test: would the
code still make sense in a completely different app?

- Checking a JWT → yes, every service does it → here.
- Creating a JWT → only the auth service may do that → stays in that service.
- A `Todo` struct, a `users` query → never here. Services share those
  over HTTP, not by importing each other's code.

Why so strict: everything in here is a change that hits **all**
services at once. The smaller this folder, the more independent the
services stay.

## How a service uses it

The library is not published anywhere; it lives in this repo. A
service's `go.mod` says so with a `replace` line:

```
require github.com/MirajHoque/todo-microservice/libs/go v0.0.0

replace github.com/MirajHoque/todo-microservice/libs/go => ../../libs/go
```

`replace` means "don't download this module, read it from that folder".
The version `v0.0.0` is only a placeholder. Then import as usual:

```go
import "github.com/MirajHoque/todo-microservice/libs/go/logger"

log := logger.New("auth", cfg.LogFormat, cfg.LogLevel, cfg.Env)
```

Because of `../../libs/go`, a service's Docker image must be built from
the **repo root**, so the build can see both folders:

```bash
docker build -f services/todo/Dockerfile -t todo-todo .
```

## Commands

```bash
cd libs/go
make test    # run the tests
make check   # go build + go vet
```
