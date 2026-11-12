// Tests for the shared health endpoints, with a fake database
// (no Postgres needed: Ready only asks for the Database interface).
package health

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

// fakeDB is reachable when err is nil.
type fakeDB struct{ err error }

func (f fakeDB) Ping(context.Context) error { return f.err }
func (f fakeDB) Stats() map[string]any      { return map[string]any{"total_conns": 2} }

func get(t *testing.T, handler http.Handler, into any) int {
	t.Helper()
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	if err := json.Unmarshal(rec.Body.Bytes(), into); err != nil {
		t.Fatalf("response is not JSON: %v\n%s", err, rec.Body.String())
	}
	return rec.Code
}

func TestLive(t *testing.T) {
	var body LiveResponse
	status := get(t, Live("auth"), &body)

	if status != http.StatusOK || body.Status != "ok" || body.Service != "auth" {
		t.Errorf("got %d %+v, want 200 ok auth", status, body)
	}
}

func TestReadyWhenTheDatabaseAnswers(t *testing.T) {
	var body ReadyResponse
	status := get(t, Ready(fakeDB{}), &body)

	if status != http.StatusOK || body.Status != "ready" || !body.Database.Connected {
		t.Errorf("got %d %+v, want 200 ready connected", status, body)
	}
}

func TestNotReadyWhenTheDatabaseIsDown(t *testing.T) {
	var body ReadyResponse
	status := get(t, Ready(fakeDB{err: errors.New("connection refused: password=hunter2")}), &body)

	if status != http.StatusServiceUnavailable || body.Status != "not ready" || body.Database.Connected {
		t.Errorf("got %d %+v, want 503 not ready", status, body)
	}
	// The real error can contain connection details: it must stay in the logs.
	if body.Database.Error != "database unreachable" {
		t.Errorf("error = %q, want the generic message", body.Database.Error)
	}
}
