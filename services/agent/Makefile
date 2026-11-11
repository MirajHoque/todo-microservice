# ============================================================
# Makefile for the agent service (Python / FastAPI)
# Usage: make <target>
#
# uv runs everything inside this service's own .venv/, created
# from pyproject.toml + uv.lock — no global pip installs.
# ============================================================

.PHONY: install dev run test lint fmt help

## install: create .venv/ and install all dependencies (first time, or after pulling)
install:
	uv sync

## dev: run with auto-reload on http://localhost:8083 (reads .env)
dev:
	uv run python -m agent

## run: run like production (no reload)
run:
	ENV=production uv run python -m agent

## test: run the tests
test:
	uv run pytest -q

## lint: check code style and likely bugs (like go vet)
lint:
	uv run ruff check .
	uv run ruff format --check .

## fmt: format the code (like gofmt)
fmt:
	uv run ruff check --fix .
	uv run ruff format .

## help: show this help message
help:
	@grep -E '^## ' Makefile | sed 's/## //'
