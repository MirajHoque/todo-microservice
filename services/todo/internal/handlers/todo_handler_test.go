// Tests for the todo endpoints — through the real router, against a
// real Postgres database (todo_db_test), with nothing faked.
//
// There is NO auth service in these tests, and none is needed: this
// service never calls it. A test "logs in" by signing a token itself
// with the test secret — exactly what makes the services independent.
//
// Needs `make db` (in the repo root). If Postgres isn't running the
// tests are SKIPPED with a message, not failed.
//
//	cd services/todo && make test
package handlers_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/MirajHoque/todo-microservice/libs/go/jwtauth"
	"github.com/MirajHoque/todo-microservice/libs/go/postgres"
	"github.com/MirajHoque/todo-microservice/libs/go/respond"
	"github.com/MirajHoque/todo-microservice/services/todo/internal/db"
	"github.com/MirajHoque/todo-microservice/services/todo/internal/handlers"
	"github.com/MirajHoque/todo-microservice/services/todo/internal/models"
	"github.com/MirajHoque/todo-microservice/services/todo/migrations"
)

const (
	testSecret  = "test-secret-at-least-32-characters-long"
	defaultTest = "postgres://todo_svc:todo_svc@localhost:5433/todo_db_test?sslmode=disable"
	todosPath   = "/api/v1/todos"
)

// newRouter builds the service exactly like main.go does, on an EMPTY
// test database.
func newRouter(t *testing.T) http.Handler {
	t.Helper()
	ctx := context.Background()
	quiet := slog.New(slog.NewTextHandler(io.Discard, nil)) // no log noise in test output

	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		url = defaultTest
	}
	database, err := postgres.Connect(ctx, postgres.Config{URL: url, MaxConns: 4}, quiet)
	if err != nil {
		t.Skipf("no test database (run `make db` in the repo root): %v", err)
	}
	t.Cleanup(database.Close)

	if err := database.Migrate(ctx, migrations.FS, quiet); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	// Every test starts with no todos.
	if _, err := database.Pool.Exec(ctx, "TRUNCATE todos"); err != nil {
		t.Fatalf("empty the todos table: %v", err)
	}

	todoHandler := handlers.NewTodoHandler(db.NewTodoRepository(database))
	return handlers.NewRouter(quiet, database, jwtauth.NewVerifier(testSecret), todoHandler)
}

// user is someone with a valid token. No row anywhere says they exist:
// the token IS the proof (this service has no users table).
type user struct {
	id    string
	token string
}

// newUser signs a token the way the auth service does.
func newUser(t *testing.T) user {
	t.Helper()
	id := uuid.NewString()
	claims := jwtauth.Claims{
		UserID: id,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			Issuer:    "todo-app",
		},
	}
	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(testSecret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return user{id: id, token: token}
}

// call sends one request as u (or as nobody when u.token is empty).
func call(router http.Handler, u user, method, path string, body any) *httptest.ResponseRecorder {
	var buf bytes.Buffer
	if s, ok := body.(string); ok {
		buf.WriteString(s) // raw text, for the "broken JSON" test
	} else if body != nil {
		json.NewEncoder(&buf).Encode(body)
	}
	req := httptest.NewRequest(method, path, &buf)
	req.Header.Set("Content-Type", "application/json")
	if u.token != "" {
		req.Header.Set("Authorization", "Bearer "+u.token)
	}
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)
	return rec
}

// decode reads a JSON response body into T.
func decode[T any](t *testing.T, rec *httptest.ResponseRecorder) T {
	t.Helper()
	var v T
	if err := json.Unmarshal(rec.Body.Bytes(), &v); err != nil {
		t.Fatalf("response is not JSON: %v\n%s", err, rec.Body.String())
	}
	return v
}

// wantError checks the status code and the standard error body.
func wantError(t *testing.T, rec *httptest.ResponseRecorder, status int, message string) {
	t.Helper()
	if rec.Code != status {
		t.Fatalf("status = %d, want %d (%s)", rec.Code, status, rec.Body.String())
	}
	body := decode[respond.ErrorBody](t, rec)
	if body.Error != message {
		t.Errorf("error = %q, want %q", body.Error, message)
	}
	if body.RequestID == "" {
		t.Error("error has no request_id")
	}
}

type M = map[string]any // short for a JSON object in the tests

// create adds a todo for u and returns it.
func create(t *testing.T, router http.Handler, u user, title string) models.Todo {
	t.Helper()
	rec := call(router, u, http.MethodPost, todosPath, M{"title": title})
	if rec.Code != http.StatusCreated {
		t.Fatalf("create %q: status = %d (%s)", title, rec.Code, rec.Body.String())
	}
	return decode[models.Todo](t, rec)
}

// titles lists u's todos and returns their titles.
func titles(t *testing.T, router http.Handler, u user) []string {
	t.Helper()
	rec := call(router, u, http.MethodGet, todosPath, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("list: status = %d (%s)", rec.Code, rec.Body.String())
	}
	out := []string{}
	for _, todo := range decode[[]models.Todo](t, rec) {
		out = append(out, todo.Title)
	}
	return out
}

// ── Create and list ──────────────────────────────────────────

func TestCreateATodo(t *testing.T) {
	router := newRouter(t)
	ali := newUser(t)

	rec := call(router, ali, http.MethodPost, todosPath, M{"title": "  Buy milk  ", "priority": "high"})

	if rec.Code != http.StatusCreated {
		t.Fatalf("status = %d, want 201 (%s)", rec.Code, rec.Body.String())
	}
	todo := decode[models.Todo](t, rec)
	if todo.ID == "" || todo.Title != "Buy milk" || todo.Priority != models.PriorityHigh || todo.Done {
		t.Errorf("todo = %+v, want an id, title 'Buy milk', priority high, not done", todo)
	}
	// The owner comes from the TOKEN — there is no user_id in the request.
	if todo.UserID != ali.id {
		t.Errorf("user_id = %q, want the token's user %q", todo.UserID, ali.id)
	}
}

func TestPriorityDefaultsToMedium(t *testing.T) {
	router := newRouter(t)
	if todo := create(t, router, newUser(t), "Call mom"); todo.Priority != models.PriorityMedium {
		t.Errorf("priority = %q, want medium", todo.Priority)
	}
}

// A user_id in the body must be ignored: otherwise anyone could write
// todos into someone else's list.
func TestCannotCreateATodoForSomeoneElse(t *testing.T) {
	router := newRouter(t)
	ali, sara := newUser(t), newUser(t)

	rec := call(router, ali, http.MethodPost, todosPath, M{"title": "sneaky", "user_id": sara.id})

	if todo := decode[models.Todo](t, rec); todo.UserID != ali.id {
		t.Errorf("user_id = %q, want the token's user %q", todo.UserID, ali.id)
	}
	if got := titles(t, router, sara); len(got) != 0 {
		t.Errorf("sara's list = %v, want empty", got)
	}
}

func TestCreateRejectsBadInput(t *testing.T) {
	router := newRouter(t)
	ali := newUser(t)

	tests := []struct {
		name    string
		body    any
		message string
	}{
		{"broken JSON", `{"title":`, "invalid request body"},
		{"no title", M{"priority": "low"}, "title is required"},
		{"only spaces", M{"title": "   "}, "title is required"},
		{"title too long", M{"title": strings.Repeat("x", 256)}, "title must be 255 characters or fewer"},
		{"unknown priority", M{"title": "x", "priority": "urgent"}, `invalid priority "urgent", must be low, medium, or high`},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			wantError(t, call(router, ali, http.MethodPost, todosPath, tt.body), http.StatusBadRequest, tt.message)
		})
	}
	if got := titles(t, router, ali); len(got) != 0 {
		t.Errorf("list = %v, want nothing created", got)
	}
}

func TestAnEmptyListIsAnEmptyArrayNotNull(t *testing.T) {
	router := newRouter(t)

	rec := call(router, newUser(t), http.MethodGet, todosPath, nil)

	// web does todos.map(...): `null` would crash the page.
	if got := strings.TrimSpace(rec.Body.String()); got != "[]" {
		t.Errorf("body = %s, want []", got)
	}
}

// ── Each user sees only their own todos ──────────────────────

func TestUsersOnlySeeTheirOwnTodos(t *testing.T) {
	router := newRouter(t)
	ali, sara := newUser(t), newUser(t)
	create(t, router, ali, "Ali's todo")
	create(t, router, sara, "Sara's todo")

	if got := titles(t, router, ali); len(got) != 1 || got[0] != "Ali's todo" {
		t.Errorf("ali's list = %v, want only his own todo", got)
	}
	if got := titles(t, router, sara); len(got) != 1 || got[0] != "Sara's todo" {
		t.Errorf("sara's list = %v, want only her own todo", got)
	}
}

// Someone else's todo answers 404 — the same as a todo that doesn't
// exist. "403 forbidden" would tell an attacker the id is real.
func TestCannotChangeOrDeleteSomeoneElsesTodo(t *testing.T) {
	router := newRouter(t)
	ali, sara := newUser(t), newUser(t)
	todo := create(t, router, ali, "Ali's todo")
	path := todosPath + "/" + todo.ID

	wantError(t, call(router, sara, http.MethodPatch, path, M{"done": true}), http.StatusNotFound, "todo not found")
	wantError(t, call(router, sara, http.MethodDelete, path, nil), http.StatusNotFound, "todo not found")

	// Still there, still untouched.
	rec := call(router, ali, http.MethodGet, todosPath, nil)
	mine := decode[[]models.Todo](t, rec)
	if len(mine) != 1 || mine[0].Done {
		t.Errorf("ali's todos = %+v, want his one todo, not done", mine)
	}
}

// ── Update ───────────────────────────────────────────────────

func TestCompleteAndReopenATodo(t *testing.T) {
	router := newRouter(t)
	ali := newUser(t)
	path := todosPath + "/" + create(t, router, ali, "Buy milk").ID

	done := decode[models.Todo](t, call(router, ali, http.MethodPatch, path, M{"done": true}))
	if !done.Done || done.DoneAt == nil {
		t.Errorf("after done=true: done=%v done_at=%v, want true and a time", done.Done, done.DoneAt)
	}

	reopened := decode[models.Todo](t, call(router, ali, http.MethodPatch, path, M{"done": false}))
	if reopened.Done || reopened.DoneAt != nil {
		t.Errorf("after done=false: done=%v done_at=%v, want false and no time", reopened.Done, reopened.DoneAt)
	}
}

// PATCH changes only the fields that were sent.
func TestUpdateChangesOnlyWhatWasSent(t *testing.T) {
	router := newRouter(t)
	ali := newUser(t)
	path := todosPath + "/" + create(t, router, ali, "Buy milk").ID

	todo := decode[models.Todo](t, call(router, ali, http.MethodPatch, path, M{"priority": "low"}))

	if todo.Priority != models.PriorityLow || todo.Title != "Buy milk" || todo.Done {
		t.Errorf("todo = %+v, want priority low and everything else unchanged", todo)
	}
}

func TestUpdateRejectsBadInput(t *testing.T) {
	router := newRouter(t)
	ali := newUser(t)
	path := todosPath + "/" + create(t, router, ali, "Buy milk").ID

	wantError(t, call(router, ali, http.MethodPatch, path, M{"title": "  "}), http.StatusBadRequest, "title is required")
	wantError(t, call(router, ali, http.MethodPatch, path, M{"priority": "urgent"}),
		http.StatusBadRequest, `invalid priority "urgent", must be low, medium, or high`)
	wantError(t, call(router, ali, http.MethodPatch, path, `{"done":`), http.StatusBadRequest, "invalid request body")

	if got := titles(t, router, ali); len(got) != 1 || got[0] != "Buy milk" {
		t.Errorf("list = %v, want the todo unchanged", got)
	}
}

// ── Delete ───────────────────────────────────────────────────

func TestDeleteATodo(t *testing.T) {
	router := newRouter(t)
	ali := newUser(t)
	path := todosPath + "/" + create(t, router, ali, "Buy milk").ID

	if rec := call(router, ali, http.MethodDelete, path, nil); rec.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want 204 (%s)", rec.Code, rec.Body.String())
	}
	if got := titles(t, router, ali); len(got) != 0 {
		t.Errorf("list = %v, want empty", got)
	}
	// Deleting it again: it's gone.
	wantError(t, call(router, ali, http.MethodDelete, path, nil), http.StatusNotFound, "todo not found")
}

// An id that isn't even a UUID (a typo, or an LLM making one up) is
// "not found" — not a database error.
func TestAnIDThatIsNotAUUIDIsNotFound(t *testing.T) {
	router := newRouter(t)
	ali := newUser(t)

	wantError(t, call(router, ali, http.MethodPatch, todosPath+"/42", M{"done": true}), http.StatusNotFound, "todo not found")
	wantError(t, call(router, ali, http.MethodDelete, todosPath+"/42", nil), http.StatusNotFound, "todo not found")
}

// ── Token and health ─────────────────────────────────────────

func TestEveryTodoRouteNeedsAToken(t *testing.T) {
	router := newRouter(t)
	nobody := user{}
	id := uuid.NewString()

	requests := []struct{ method, path string }{
		{http.MethodGet, todosPath},
		{http.MethodPost, todosPath},
		{http.MethodPatch, todosPath + "/" + id},
		{http.MethodDelete, todosPath + "/" + id},
	}
	for _, r := range requests {
		t.Run(r.method, func(t *testing.T) {
			wantError(t, call(router, nobody, r.method, r.path, M{"title": "x"}),
				http.StatusUnauthorized, "missing authorization header")
		})
	}
	wantError(t, call(router, user{token: "not-a-token"}, http.MethodGet, todosPath, nil),
		http.StatusUnauthorized, "token is invalid")
}

func TestHealthEndpointsNeedNoToken(t *testing.T) {
	router := newRouter(t)
	for _, path := range []string{"/health", "/health/ready"} {
		if rec := call(router, user{}, http.MethodGet, path, nil); rec.Code != http.StatusOK {
			t.Errorf("GET %s: status = %d, want 200 (%s)", path, rec.Code, rec.Body.String())
		}
	}
}
