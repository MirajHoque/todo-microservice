// routes.go — the todo service's URL map: which path runs which handler.
//
//	GET    /health                is the process alive?
//	GET    /health/ready          can it reach its database?
//	GET    /api/v1/todos          list my todos          ┐
//	POST   /api/v1/todos          create a todo          │ all need a
//	PATCH  /api/v1/todos/{id}     change one of my todos │ valid token
//	DELETE /api/v1/todos/{id}     delete one of my todos ┘
//
// The paths start with /api/v1/todos because that is what the callers
// use: web's proxy.ts (later: the Kubernetes gateway) sends everything
// under /api/v1/todos here, and the agent calls this service directly.
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
const ServiceName = "todo"

// NewRouter wires the middleware and the routes together.
func NewRouter(
	log *slog.Logger,
	database health.Database,
	verifier *jwtauth.Verifier,
	todoHandler *TodoHandler,
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

	// API — every route needs a valid token. The shared JWT check runs
	// first and puts the user's id into the request; the handlers read
	// it from there and never from the request body or the URL.
	r.Route("/api/v1/todos", func(r chi.Router) {
		r.Use(verifier.Middleware)

		r.Post("/", todoHandler.Create)
		r.Get("/", todoHandler.List)
		r.Patch("/{id}", todoHandler.Update)
		r.Delete("/{id}", todoHandler.Delete)
	})

	return r
}
