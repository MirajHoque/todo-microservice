# ============================================================
# Makefile for libs/go — the Go code shared by every Go service.
#
# A library has nothing to run (no main.go, no port, no .env):
# you only build, check and test it.
#
#   make test   → run the tests
#   make check  → build + vet (what a service does before using it)
# ============================================================

.PHONY: test check tidy help

## test: run all tests with the race detector
test:
	go test -race ./...

## check: compile and vet every package
check:
	go build ./...
	go vet ./...

## tidy: tidy and verify go modules
tidy:
	go mod tidy
	go mod verify

## help: show this help message
help:
	@grep -E '^## ' Makefile | sed 's/## //'
