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

	"github.com/go-chi/chi/v5"
	chimiddleware "github.com/go-chi/chi/v5/middleware"

	// Shared code (libs/go): the same packages every Go service will use.
	"github.com/MirajHoque/todo-microservice/libs/go/jwtauth"
	"github.com/MirajHoque/todo-microservice/libs/go/logger"
	"github.com/MirajHoque/todo-microservice/libs/go/middleware"

	"github.com/MirajHoque/todo-microservice/services/api/internal/auth"
	"github.com/MirajHoque/todo-microservice/services/api/internal/config"
	"github.com/MirajHoque/todo-microservice/services/api/internal/db"
	"github.com/MirajHoque/todo-microservice/services/api/internal/handlers"
	"github.com/MirajHoque/todo-microservice/services/api/migrations"
	"github.com/MirajHoque/todo-microservice/services/api/web"
	// <pathOftheModule>/<packageWantToImport>
)

// version is set at build time: -ldflags "-X main.version=1.2.3"
var version = "dev"

func main() {
	// `todo-app healthcheck` is used by the Docker HEALTHCHECK.
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
	log := logger.New("todo-app", cfg.LogFormat, cfg.LogLevel, cfg.Env)
	log.Info("starting todo-app",
		slog.String("version", version),
		slog.String("env", cfg.Env),
		slog.String("addr", cfg.Addr()),
	)

	// ── 3. Database ────────────────────────────────────────────────────────
	ctx := context.Background()

	database, err := db.Connect(ctx, cfg, log)
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
	// Two halves of JWT: jwtService CREATES tokens (login/register — auth
	// only), jwtVerifier CHECKS them (shared library, every service).
	jwtService := auth.NewService(cfg.JWTSecret, cfg.JWTExpiry)
	jwtVerifier := jwtauth.NewVerifier(cfg.JWTSecret)
	userRepo := db.NewUserRepository(database)
	todoRepo := db.NewTodoRepository(database)

	// The AI agent used to live here (internal/agents). Since step 2f it
	// is its own service: services/agent (Python), on port 8083.

	// ── 6. Handlers ────────────────────────────────────────────────────────
	authHandler := handlers.NewAuthHandler(userRepo, jwtService)
	todoHandler := handlers.NewTodoHandler(todoRepo)
	pageHandler := handlers.NewPageHandler(web.FS)

	// ── 7. Router ──────────────────────────────────────────────────────────
	r := chi.NewRouter()

	r.Use(middleware.RequestID)
	r.Use(middleware.Logger(log))
	r.Use(middleware.Recoverer)
	r.Use(middleware.RequestLog)
	r.Use(chimiddleware.StripSlashes)

	// HTML pages
	r.Get("/", pageHandler.LoginPage)
	r.Get("/register", pageHandler.RegisterPage)
	r.Get("/todos", pageHandler.TodosPage)

	// Health
	r.Get("/health", handlers.Health)
	r.Get("/health/ready", handlers.NewHealthReady(database))

	// API
	r.Route("/api/v1", func(r chi.Router) {
		// Public
		r.Post("/auth/register", authHandler.Register)
		r.Post("/auth/login", authHandler.Login)

		// Protected
		r.Group(func(r chi.Router) {
			r.Use(jwtVerifier.Middleware)

			// Auth
			r.Post("/auth/logout", authHandler.Logout)

			// Todos
			r.Post("/todos", todoHandler.Create)
			r.Get("/todos", todoHandler.List)
			r.Patch("/todos/{id}", todoHandler.Update)
			r.Delete("/todos/{id}", todoHandler.Delete)
		})
	})

	// ── 8. HTTP server with graceful shutdown ──────────────────────────────
	srv := &http.Server{
		Addr:         cfg.Addr(),
		Handler:      r,
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
		port = "8080"
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
