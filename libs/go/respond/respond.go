// Package respond writes JSON responses the same way in every Go service.
//
// SHARED CODE (libs/go): generic only (ROADMAP rule 4).
//
// The important part is the ERROR shape. Every service — Go and the
// Python agent — answers an error with the same two fields:
//
//	{"error": "what went wrong", "request_id": "550e8400-…"}
//
// web shows `error` to the user; `request_id` is what you search for
// in the logs to find out what happened. Because the shape is a
// contract between services, it is defined once, here.
package respond

import (
	"encoding/json"
	"log/slog"
	"net/http"

	"github.com/MirajHoque/todo-microservice/libs/go/middleware"
)

// ErrorBody is the standard error envelope returned on 4xx/5xx.
type ErrorBody struct {
	Error     string `json:"error"`
	RequestID string `json:"request_id,omitempty"`
}

// JSON encodes v as JSON and writes it with the given status code.
// Every handler uses this — it ensures we always set Content-Type correctly.
func JSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		// At this point we've already written the header, so we can't change
		// the status. Just log it.
		slog.Error("respond: encode failed", slog.String("error", err.Error()))
	}
}

// Error writes the standard error envelope.
// The request_id comes from the request context (middleware.RequestID put it there).
func Error(w http.ResponseWriter, r *http.Request, status int, msg string) {
	JSON(w, status, ErrorBody{
		Error:     msg,
		RequestID: middleware.GetRequestID(r.Context()),
	})
}
