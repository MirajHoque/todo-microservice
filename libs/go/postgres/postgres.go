// Package postgres opens a PostgreSQL connection pool and runs migrations.
//
// SHARED CODE (libs/go): generic only (ROADMAP rule 4). This package
// knows HOW to talk to a Postgres database — not WHICH database, and
// nothing about its tables. Each service passes in its own
// DATABASE_URL and its own migration files, and keeps its own SQL
// queries (its "repositories") inside the service.
//
//	auth service ── postgres.Connect(auth_db) ── users queries live in services/auth
//	todo service ── postgres.Connect(todo_db) ── todos queries live in services/todo
//
// WHY pgx INSTEAD OF database/sql?
// pgx is a PostgreSQL-specific driver that gives us:
//   - Native support for PostgreSQL types (UUID, TIMESTAMPTZ, arrays)
//   - Better performance than database/sql
//   - pgxpool for connection pooling (essential for web apps)
//   - Cleaner error handling with pgconn.PgError
//
// CONNECTION POOL
// A pool keeps N connections open and ready.
// Without a pool, every request opens a new TCP connection to
// PostgreSQL — expensive (100-300ms each time on Azure).
// With a pool, connections are reused — near zero overhead.
package postgres

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/MirajHoque/todo-microservice/libs/go/logger"
)

// Config is what Connect needs. Each service fills it from its own
// environment variables (DATABASE_URL, DB_MAX_CONNS, …).
type Config struct {
	URL         string        // postgres://user:password@host:port/database
	MaxConns    int32         // most connections the pool may open
	MinConns    int32         // connections kept open even when idle
	MaxConnIdle time.Duration // close a connection that was unused this long
}

// DB wraps pgxpool.Pool so we can add methods to it.
// All database operations in a service go through this type.
type DB struct {
	Pool *pgxpool.Pool
}

// Connect creates a connection pool.
// Call this once at startup in main.go.
// Returns an error if the database is unreachable — the app should not start.
func Connect(ctx context.Context, cfg Config, log *slog.Logger) (*DB, error) {
	log.Info("connecting to database",
		slog.String(logger.FieldAction, "db_connect"),
	)

	// Parse the DATABASE_URL into a pgx pool config.
	poolCfg, err := pgxpool.ParseConfig(cfg.URL)
	if err != nil {
		return nil, fmt.Errorf("postgres: parse config: %w", err)
	}

	// Connection pool settings — tune these for your workload.
	poolCfg.MaxConns = cfg.MaxConns
	poolCfg.MinConns = cfg.MinConns
	poolCfg.MaxConnIdleTime = cfg.MaxConnIdle

	// Replace every connection after an hour, so none lives forever.
	poolCfg.MaxConnLifetime = 1 * time.Hour

	// Create the pool. This does NOT open connections yet —
	// connections are opened lazily on first use.
	pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		return nil, fmt.Errorf("postgres: create pool: %w", err)
	}

	// Ping verifies we can actually reach the database.
	// This is the moment we find out if DATABASE_URL is wrong.
	pingCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	if err := pool.Ping(pingCtx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("postgres: ping failed: %w", err)
	}

	log.Info("database connected",
		slog.String(logger.FieldAction, "db_connected"),
		slog.String("database", poolCfg.ConnConfig.Database),
		slog.Int("max_conns", int(cfg.MaxConns)),
		slog.Int("min_conns", int(cfg.MinConns)),
	)

	return &DB{Pool: pool}, nil
}

// Close shuts down the connection pool cleanly.
// Call this in main.go during graceful shutdown.
func (db *DB) Close() {
	db.Pool.Close()
}

// Ping checks if the database is still reachable.
// Used by the /health/ready endpoint.
func (db *DB) Ping(ctx context.Context) error {
	pingCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	return db.Pool.Ping(pingCtx)
}

// Stats returns connection pool statistics for monitoring.
// The health endpoint returns them so you can see them in Grafana.
func (db *DB) Stats() map[string]any {
	stats := db.Pool.Stat()
	return map[string]any{
		"total_conns":    stats.TotalConns(),
		"idle_conns":     stats.IdleConns(),
		"acquired_conns": stats.AcquiredConns(),
		"max_conns":      stats.MaxConns(),
	}
}
