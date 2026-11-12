// main.go — starts the auth service (port 8081).
//
// The auth service owns the users (database auth_db) and is the ONLY
// service that creates JWTs:
//
//	register / login ──▶ auth ──▶ token ──▶ browser
//	browser ── token ──▶ todo, agent …  (they only CHECK it, with the
//	                                     same JWT_SECRET)
//
// What main does, in order: read config → logger → connect to the
// database → run migrations → build the handlers → start the HTTP
// server → wait for Ctrl+C and shut down cleanly.
//
// Almost everything generic (logger, middleware, database pool,
// migrations, health endpoints, JWT check) comes from the shared
// library libs/go. What is left in this service is what makes it the
// AUTH service: users, passwords, creating tokens.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	// Shared code (libs/go): the same packages every Go service uses.
	"github.com/MirajHoque/todo-microservice/libs/go/jwtauth"
	"github.com/MirajHoque/todo-microservice/libs/go/logger"
	"github.com/MirajHoque/todo-microservice/libs/go/postgres"

	// This service's own code. No other service may import these
	// (Go enforces it: "internal" packages are private to the module).
	"github.com/MirajHoque/todo-microservice/services/auth/internal/auth"
	"github.com/MirajHoque/todo-microservice/services/auth/internal/config"
	"github.com/MirajHoque/todo-microservice/services/auth/internal/db"
	"github.com/MirajHoque/todo-microservice/services/auth/internal/handlers"
	"github.com/MirajHoque/todo-microservice/services/auth/migrations"
)

// version is set at build time: -ldflags "-X main.version=1.2.3"
var version = "dev"

func main() {
	// `auth healthcheck` is used by the Docker HEALTHCHECK.
	// The runtime image has no shell or wget, so the binary checks itself.
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		os.Exit(healthcheck())
	}

	// ── 1. Config ─────────────────────────────────────────────────────────
	cfg, err := config.Load()
	if err != nil {
		slog.Error("failed to load config", slog.String("error", err.Error()))
		os.Exit(1)
	}

	// ── 2. Logger ──────────────────────────────────────────────────────────
	log := logger.New(handlers.ServiceName, cfg.LogFormat, cfg.LogLevel, cfg.Env)
	log.Info("starting auth service",
		slog.String("version", version),
		slog.String("env", cfg.Env),
		slog.String("addr", cfg.Addr()),
	)

	// ── 3. Database ────────────────────────────────────────────────────────
	ctx := context.Background()

	database, err := postgres.Connect(ctx, postgres.Config{
		URL:         cfg.DatabaseURL,
		MaxConns:    cfg.DBMaxConns,
		MinConns:    cfg.DBMinConns,
		MaxConnIdle: cfg.DBMaxConnIdle,
	}, log)
	if err != nil {
		log.Error("failed to connect to database",
			slog.String(logger.FieldError, err.Error()),
		)
		os.Exit(1)
	}
	defer database.Close()

	// ── 4. Migrations ──────────────────────────────────────────────────────
	if err := database.Migrate(ctx, migrations.FS, log); err != nil {
		log.Error("failed to run migrations",
			slog.String(logger.FieldError, err.Error()),
		)
		os.Exit(1)
	}

	// ── 5. Services & repositories ─────────────────────────────────────────
	// Two halves of JWT: jwtService CREATES tokens (only this service),
	// jwtVerifier CHECKS them (shared library, every service).
	jwtService := auth.NewService(cfg.JWTSecret, cfg.JWTExpiry)
	jwtVerifier := jwtauth.NewVerifier(cfg.JWTSecret)
	userRepo := db.NewUserRepository(database)

	// ── 6. Handlers and routes (internal/handlers/routes.go) ───────────────
	authHandler := handlers.NewAuthHandler(userRepo, jwtService, cfg.BCryptCost)
	router := handlers.NewRouter(log, database, jwtVerifier, authHandler)

	// ── 7. HTTP server with graceful shutdown ──────────────────────────────
	srv := &http.Server{
		Addr:         cfg.Addr(),
		Handler:      router,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		IdleTimeout:  cfg.IdleTimeout,
		ErrorLog:     slog.NewLogLogger(log.Handler(), slog.LevelError),
	}

	serverErr := make(chan error, 1)
	go func() {
		log.Info("http server listening", slog.String("addr", cfg.Addr()))
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			serverErr <- err
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case err := <-serverErr:
		log.Error("server error", slog.String(logger.FieldError, err.Error()))
		os.Exit(1)
	case sig := <-quit:
		log.Info("shutdown signal received", slog.String("signal", sig.String()))
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Error("graceful shutdown failed", slog.String(logger.FieldError, err.Error()))
		os.Exit(1)
	}

	log.Info("server stopped cleanly")
}

// healthcheck calls GET /health on the local server.
// Returns 0 if healthy, 1 otherwise (the exit codes Docker expects).
func healthcheck() int {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8081"
	}

	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get("http://127.0.0.1:" + port + "/health")
	if err != nil {
		return 1
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return 1
	}
	return 0
}
