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
#   make psql-auth               → psql shell in the auth service's database (auth_db)
#   make psql-todo               → psql shell in the todo service's database (todo_db)
#   make psql-agent              → psql shell in the agent's database (agent_db)
#   make psql                    → psql shell as the admin, in the old monolith database (todo)
#   make db-copy-users           → one-time: copy users from the old database to auth_db
#   make db-copy-todos           → one-time: copy todos from the old database to todo_db
#   make db-stop                 → stop Postgres (data is kept)
#   make db-reset                → delete Postgres and all its data
#
# compose.yaml is parked until all services exist (ROADMAP).
#   make up / make down / make logs → whole system via compose
# ============================================================

SERVICE ?= todo
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

.PHONY: db db-init db-copy-users db-copy-todos db-stop db-reset psql psql-auth psql-todo psql-agent up down logs svc help

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
	@echo "✓ Databases ready: auth_db (user auth), todo_db (user todo_svc), agent_db (user agent) — each with a _test twin"

## db-copy-users: one-time (step 3b): copy the users from the old monolith database (todo) to auth_db
#  Users used to live in the monolith's database; now the auth service owns
#  them. This copies every account (same id, same password hash), so
#  people can still log in and their todos still belong to them.
#
#  How: the first psql prints the users as text (COPY … TO STDOUT), the
#  "|" pipes that text into a second psql connected to auth_db, which
#  reads it into a temporary table and inserts the rows that are not
#  there yet. Safe to run again: existing users are skipped.
#  Start the auth service once before this — it creates the users table.
#  It runs as the `todo` superuser, the only user allowed into both
#  databases; the services themselves can't do this (and shouldn't).
USER_COLUMNS := id, email, password_hash, created_at, updated_at
db-copy-users:
	@docker exec $(DB_CONTAINER) psql -q -v ON_ERROR_STOP=1 -U $(DB_USER) -d $(DB_NAME) \
		-c "COPY (SELECT $(USER_COLUMNS) FROM users) TO STDOUT" \
	| docker exec -i $(DB_CONTAINER) psql -q -v ON_ERROR_STOP=1 -U $(DB_USER) -d auth_db \
		-c "CREATE TEMP TABLE incoming (LIKE users)" \
		-c "COPY incoming ($(USER_COLUMNS)) FROM STDIN" \
		-c "INSERT INTO users ($(USER_COLUMNS)) SELECT $(USER_COLUMNS) FROM incoming ON CONFLICT DO NOTHING"
	@echo "✓ Users in auth_db: $$(docker exec $(DB_CONTAINER) psql -tA -U $(DB_USER) -d auth_db -c 'SELECT count(*) FROM users')" \
		"(old database: $$(docker exec $(DB_CONTAINER) psql -tA -U $(DB_USER) -d $(DB_NAME) -c 'SELECT count(*) FROM users'))"

## db-stop: stop Postgres (data stays in the volume)
db-stop:
	docker stop $(DB_CONTAINER)

## db-reset: delete the Postgres container AND its data volume
db-reset:
	-docker rm -f $(DB_CONTAINER)
	-docker volume rm $(DB_VOLUME)

## db-copy-todos: one-time (step 3c): copy the todos from the old monolith database (todo) to todo_db
#  Same idea as db-copy-users: print the rows as text from one database,
#  pipe them into the other. Ids are kept, so every todo still belongs
#  to the same user and the agent's memory still points at the right todos.
#  Safe to run again: todos that are already there are skipped.
#  Start the todo service once before this — it creates the todos table.
TODO_COLUMNS := id, user_id, title, description, priority, done, done_at, created_at, updated_at
db-copy-todos:
	@docker exec $(DB_CONTAINER) psql -q -v ON_ERROR_STOP=1 -U $(DB_USER) -d $(DB_NAME) \
		-c "COPY (SELECT $(TODO_COLUMNS) FROM todos) TO STDOUT" \
	| docker exec -i $(DB_CONTAINER) psql -q -v ON_ERROR_STOP=1 -U $(DB_USER) -d todo_db \
		-c "CREATE TEMP TABLE incoming (LIKE todos)" \
		-c "COPY incoming ($(TODO_COLUMNS)) FROM STDIN" \
		-c "INSERT INTO todos ($(TODO_COLUMNS)) SELECT $(TODO_COLUMNS) FROM incoming ON CONFLICT DO NOTHING"
	@echo "✓ Todos in todo_db: $$(docker exec $(DB_CONTAINER) psql -tA -U $(DB_USER) -d todo_db -c 'SELECT count(*) FROM todos')" \
		"(old database: $$(docker exec $(DB_CONTAINER) psql -tA -U $(DB_USER) -d $(DB_NAME) -c 'SELECT count(*) FROM todos'))"

## psql: open a psql shell as the admin user, in the old monolith database (todo)
psql:
	docker exec -it $(DB_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME)

## psql-todo: open a psql shell in the todo service's database, as its user
psql-todo:
	docker exec -it $(DB_CONTAINER) psql -U todo_svc -d todo_db

## psql-auth: open a psql shell in the auth service's database, as the auth user
psql-auth:
	docker exec -it $(DB_CONTAINER) psql -U auth -d auth_db

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
