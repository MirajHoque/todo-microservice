// routes.go — the auth service's URL map: which path runs which handler.
//
//	GET  /health                  is the process alive?
//	GET  /health/ready            can it reach its database?
//	POST /api/v1/auth/register    public
//	POST /api/v1/auth/login       public
//	POST /api/v1/auth/logout      needs a valid token
//
// The paths start with /api/v1/auth because that is what the browser
// calls. web's proxy.ts (later: the Kubernetes gateway) sends everything
// under /api/v1/auth to this service without changing the path.
//
// The router is built in its own function (not inside main.go) so the
// tests can build exactly the same router and send requests to it.
package handlers

import (
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	chimiddleware "github.com/go-chi/chi/v5/middleware"

	"github.com/MirajHoque/todo-microservice/libs/go/health"
	"github.com/MirajHoque/todo-microservice/libs/go/jwtauth"
	"github.com/MirajHoque/todo-microservice/libs/go/middleware"
)

// ServiceName is this service's name in logs and in GET /health.
const ServiceName = "auth"

// NewRouter wires the middleware and the routes together.
func NewRouter(
	log *slog.Logger,
	database health.Database,
	verifier *jwtauth.Verifier,
	authHandler *AuthHandler,
) http.Handler {
	r := chi.NewRouter()

	// Shared middleware (libs/go) — the same chain in every Go service.
	r.Use(middleware.RequestID)
	r.Use(middleware.Logger(log))
	r.Use(middleware.Recoverer)
	r.Use(middleware.RequestLog)
	r.Use(chimiddleware.StripSlashes)

	// Health
	r.Get("/health", health.Live(ServiceName))
	r.Get("/health/ready", health.Ready(database))

	// API
	r.Route("/api/v1/auth", func(r chi.Router) {
		// Public: you can't have a token before you log in.
		r.Post("/register", authHandler.Register)
		r.Post("/login", authHandler.Login)

		// Protected: the shared JWT check runs first.
		r.Group(func(r chi.Router) {
			r.Use(verifier.Middleware)
			r.Post("/logout", authHandler.Logout)
		})
	})

	return r
}
