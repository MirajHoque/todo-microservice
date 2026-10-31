# ============================================================
# Root Makefile — runs the whole system or one service.
# Each service also has its own Makefile in services/<name>/.
#
# Usage:
#   make up                      → start all services (docker compose)
#   make down                    → stop all services
#   make logs                    → tail all logs
#   make svc SERVICE=api CMD=dev → run a target inside one service
# ============================================================

SERVICE ?= api
CMD     ?= build

.PHONY: up down logs svc help

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
