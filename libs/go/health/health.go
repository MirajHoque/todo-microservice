// Package health provides the two health endpoints every service has.
//
// SHARED CODE (libs/go): generic only (ROADMAP rule 4).
//
// TWO HEALTH ENDPOINTS — why?
//
//	GET /health       → "is the process alive?" (liveness probe)
//	                    Returns 200 immediately. No DB check.
//	                    If this fails, the process is dead — restart it.
//
//	GET /health/ready → "is the service ready to serve traffic?" (readiness probe)
//	                    Checks DB connectivity.
//	                    If this fails, stop sending it requests, but don't
//	                    restart it — it might be a short DB problem.
//
// Kubernetes asks every service these same two questions (step 4), so
// every service answers them the same way. The Python agent has the
// same two endpoints with the same JSON.
package health

import (
	"context"
	"log/slog"
	"net/http"
	"time"

	"github.com/MirajHoque/todo-microservice/libs/go/logger"
	"github.com/MirajHoque/todo-microservice/libs/go/respond"
)

// LiveResponse is what GET /health returns.
type LiveResponse struct {
	Status    string `json:"status"`
	Service   string `json:"service"`
	Timestamp string `json:"timestamp"`
}

// ReadyResponse is what GET /health/ready returns.
type ReadyResponse struct {
	Status    string         `json:"status"`
	Timestamp string         `json:"timestamp"`
	Database  DatabaseStatus `json:"database"`
}

// DatabaseStatus is the "database" part of ReadyResponse.
type DatabaseStatus struct {
	Connected bool           `json:"connected"`
	Stats     map[string]any `json:"stats,omitempty"`
	Error     string         `json:"error,omitempty"`
}

// Database is what Ready needs from a database: "can you reach it?"
// and some numbers. postgres.DB has both methods, so it fits — but
// this package doesn't import postgres. In Go, a type satisfies an
// interface just by having the methods; that keeps packages independent
// and lets tests pass in a fake.
type Database interface {
	Ping(ctx context.Context) error
	Stats() map[string]any
}

// Live returns the handler for GET /health.
// service is the name shown in the answer ("auth", "todo").
func Live(service string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		respond.JSON(w, http.StatusOK, LiveResponse{
			Status:    "ok",
			Service:   service,
			Timestamp: time.Now().UTC().Format(time.RFC3339),
		})
	}
}

// Ready returns the handler for GET /health/ready.
// The database is passed in as a dependency — the handler doesn't create it.
func Ready(db Database) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		log := logger.FromContext(r.Context())

		resp := ReadyResponse{
			Timestamp: time.Now().UTC().Format(time.RFC3339),
		}

		if err := db.Ping(r.Context()); err != nil {
			log.Error("readiness check failed — database unreachable",
				slog.String(logger.FieldError, err.Error()),
				slog.String(logger.FieldAction, "health_ready_fail"),
			)

			resp.Status = "not ready"
			resp.Database = DatabaseStatus{
				Connected: false,
				Error:     "database unreachable", // details stay in the log
			}
			respond.JSON(w, http.StatusServiceUnavailable, resp)
			return
		}

		resp.Status = "ready"
		resp.Database = DatabaseStatus{
			Connected: true,
			Stats:     db.Stats(),
		}
		respond.JSON(w, http.StatusOK, resp)
	}
}
