# ============================================================
# Root Makefile — runs the whole system or one service.
# Each service also has its own Makefile in services/<name>/.
#
# Day-to-day (database in Docker, services on your Mac):
#   make db                      → start only Postgres (Docker)
#   make svc SERVICE=api CMD=dev → run one service natively
#   make psql                    → open a psql shell in the database
#   make db-stop                 → stop Postgres (data is kept)
#
# Everything in Docker (optional, see docs/LOCAL_DEV.md):
#   make up                      → start all services (docker compose)
#   make down                    → stop all services
#   make logs                    → tail all logs
# ============================================================

SERVICE ?= api
CMD     ?= build

.PHONY: db db-stop psql up down logs svc help

## db: start only Postgres in Docker and wait until it is healthy
db:
	docker compose up -d --wait postgres

## db-stop: stop Postgres (data stays in the pgdata volume)
db-stop:
	docker compose stop postgres

## psql: open a psql shell in the local database
psql:
	docker exec -it todo-postgres psql -U todo -d todo

## up: build and start all services in the background
up:
	docker compose up -d --build

## down: stop all services
down:
	docker compose down

## logs: tail logs of all services
logs:
	docker compose logs -f

## svc: run a Makefile target in one service (SERVICE=api CMD=test)
svc:
	$(MAKE) -C services/$(SERVICE) $(CMD)

## help: show this help message
help:
	@grep -E '^## ' Makefile | sed 's/## //'
