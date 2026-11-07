# ============================================================
# Root Makefile — runs the database and helps run each service.
# Each service also has its own Makefile in services/<name>/.
#
# Day to day we run every service natively, one terminal each,
# so you see how they start, log and find each other
# (see docs/LOCAL_DEV.md). Only Postgres runs in Docker.
#
#   make db                      → start Postgres (plain docker run)
#                                  + create each service's user/database
#   make svc SERVICE=api CMD=dev → run one service natively
#   make psql                    → psql shell in the api's database (todo)
#   make psql-agent              → psql shell in the agent's database (agent_db)
#   make db-stop                 → stop Postgres (data is kept)
#   make db-reset                → delete Postgres and all its data
#
# compose.yaml is parked until all services exist (ROADMAP).
#   make up / make down / make logs → whole system via compose
# ============================================================

SERVICE ?= api
CMD     ?= build

# ── Local Postgres settings ──────────────────────────────────
# Local-only credentials — this database is never reachable from
# outside your machine. Host port 5433 because a Postgres installed
# on the Mac already uses 5432. services/<name>/.env points here.
DB_CONTAINER := todo-postgres
DB_IMAGE     := postgres:18-alpine
DB_VOLUME    := todo-pgdata
DB_PORT      := 5433
DB_USER      := todo
DB_PASSWORD  := todo
DB_NAME      := todo

.PHONY: db db-init db-stop db-reset psql psql-agent up down logs svc help

## db: start Postgres in Docker (creates it the first time) and wait until ready
#  First run: `docker run` downloads the image (if needed) and creates the
#  container; Postgres then creates the user + database from the -e vars.
#  Later runs: the container already exists, so `docker start` just starts it.
#  -v names the volume, so data survives deleting the container.
db:
	@docker start $(DB_CONTAINER) >/dev/null 2>&1 || \
	docker run -d --name $(DB_CONTAINER) \
		-e POSTGRES_USER=$(DB_USER) \
		-e POSTGRES_PASSWORD=$(DB_PASSWORD) \
		-e POSTGRES_DB=$(DB_NAME) \
		-p $(DB_PORT):5432 \
		-v $(DB_VOLUME):/var/lib/postgresql \
		--health-cmd "pg_isready -U $(DB_USER) -d $(DB_NAME)" \
		--health-interval 5s \
		$(DB_IMAGE) >/dev/null
	@echo "→ Waiting for Postgres..."
	@until docker exec $(DB_CONTAINER) pg_isready -U $(DB_USER) -d $(DB_NAME) >/dev/null 2>&1; do sleep 1; done
	@echo "✓ Postgres ready on localhost:$(DB_PORT) (user/password/db: $(DB_USER))"
	@$(MAKE) --no-print-directory db-init

## db-init: create each service's user + database (safe to re-run; see db/init.sql)
db-init:
	@docker exec -i $(DB_CONTAINER) psql -q -v ON_ERROR_STOP=1 -U $(DB_USER) -d postgres < db/init.sql
	@echo "✓ Databases ready: todo (user todo), agent_db + agent_db_test (user agent)"

## db-stop: stop Postgres (data stays in the volume)
db-stop:
	docker stop $(DB_CONTAINER)

## db-reset: delete the Postgres container AND its data volume
db-reset:
	-docker rm -f $(DB_CONTAINER)
	-docker volume rm $(DB_VOLUME)

## psql: open a psql shell in the api's database (todo)
psql:
	docker exec -it $(DB_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME)

## psql-agent: open a psql shell in the agent's database, as the agent user
psql-agent:
	docker exec -it $(DB_CONTAINER) psql -U agent -d agent_db

## up: (later) build and start all services with docker compose
up:
	docker compose up -d --build

## down: (later) stop all compose services
down:
	docker compose down

## logs: (later) tail logs of all compose services
logs:
	docker compose logs -f

## svc: run a Makefile target in one service (SERVICE=api CMD=test)
svc:
	$(MAKE) -C services/$(SERVICE) $(CMD)

## help: show this help message
help:
	@grep -E '^## ' Makefile | sed 's/## //'
