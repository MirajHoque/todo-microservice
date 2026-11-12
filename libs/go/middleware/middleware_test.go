// Tests for the shared HTTP middleware.
//
// httptest gives us a fake request and a recorder that captures the
// response — no real server or port needed.
package middleware

import (
	"bytes"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRequestIDIsCreatedAndEchoed(t *testing.T) {
	var seen string
	handler := RequestID(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = GetRequestID(r.Context())
	}))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))

	if seen == "" {
		t.Fatal("handler saw no request id")
	}
	if got := rec.Header().Get("X-Request-ID"); got != seen {
		t.Errorf("response header = %q, want %q", got, seen)
	}
}

// Another service (web, the agent) already gave the request an id:
// keep it, so one id follows the request through every service.
func TestRequestIDFromTheCallerIsKept(t *testing.T) {
	var seen string
	handler := RequestID(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = GetRequestID(r.Context())
	}))
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("X-Request-ID", "from-the-agent")

	handler.ServeHTTP(httptest.NewRecorder(), req)

	if seen != "from-the-agent" {
		t.Errorf("request id = %q, want from-the-agent", seen)
	}
}

// The full chain, as a service's main.go builds it: one JSON log line
// per request with the request id, method, path and status.
func TestRequestLogWritesOneLineWithStatusAndRequestID(t *testing.T) {
	var logs bytes.Buffer
	base := slog.New(slog.NewJSONHandler(&logs, nil))

	teapot := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTeapot)
	})
	handler := RequestID(Logger(base)(RequestLog(teapot)))

	req := httptest.NewRequest(http.MethodPost, "/api/v1/todos", nil)
	req.Header.Set("X-Request-ID", "req-1")
	handler.ServeHTTP(httptest.NewRecorder(), req)

	var line map[string]any
	if err := json.Unmarshal(logs.Bytes(), &line); err != nil {
		t.Fatalf("log output is not one JSON line: %v\n%s", err, logs.String())
	}
	want := map[string]any{
		"msg":        "request completed",
		"request_id": "req-1",
		"method":     "POST",
		"path":       "/api/v1/todos",
		"status":     float64(http.StatusTeapot), // JSON numbers decode as float64
	}
	for key, value := range want {
		if line[key] != value {
			t.Errorf("log field %s = %v, want %v", key, line[key], value)
		}
	}
}

func TestRecovererTurnsAPanicInto500(t *testing.T) {
	handler := Recoverer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		panic("boom")
	}))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil)) // must not crash the test

	if rec.Code != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500", rec.Code)
	}
}

func TestUserIDRoundTrip(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	if got := GetUserID(req.Context()); got != "" {
		t.Errorf("user id without login = %q, want empty", got)
	}
	ctx := SetUserID(req.Context(), "user-1")
	if got := GetUserID(ctx); got != "user-1" {
		t.Errorf("user id = %q, want user-1", got)
	}
}
