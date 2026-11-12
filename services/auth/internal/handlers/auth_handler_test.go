// Tests for the auth endpoints — through the real router, against a
// real Postgres database (auth_db_test), with nothing faked.
//
// Why a real database? The interesting rules live there: "an email can
// only register once" is a UNIQUE constraint, not Go code. A fake
// database would only test the fake.
//
// Needs `make db` (in the repo root). If Postgres isn't running the
// tests are SKIPPED with a message, not failed.
//
//	cd services/auth && make test
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
	"testing"
	"time"

	"golang.org/x/crypto/bcrypt"

	"github.com/MirajHoque/todo-microservice/libs/go/jwtauth"
	"github.com/MirajHoque/todo-microservice/libs/go/postgres"
	"github.com/MirajHoque/todo-microservice/libs/go/respond"
	"github.com/MirajHoque/todo-microservice/services/auth/internal/auth"
	"github.com/MirajHoque/todo-microservice/services/auth/internal/db"
	"github.com/MirajHoque/todo-microservice/services/auth/internal/handlers"
	"github.com/MirajHoque/todo-microservice/services/auth/internal/models"
	"github.com/MirajHoque/todo-microservice/services/auth/migrations"
)

const (
	testSecret  = "test-secret-at-least-32-characters-long"
	defaultTest = "postgres://auth:auth@localhost:5433/auth_db_test?sslmode=disable"
)

// app is the service under test: the router plus what the tests need
// to look behind it.
type app struct {
	router   http.Handler
	database *postgres.DB
	verifier *jwtauth.Verifier
}

// newApp builds the service exactly like main.go does, on an EMPTY
// test database.
func newApp(t *testing.T) *app {
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
	// Every test starts with no users.
	if _, err := database.Pool.Exec(ctx, "TRUNCATE users"); err != nil {
		t.Fatalf("empty the users table: %v", err)
	}

	verifier := jwtauth.NewVerifier(testSecret)
	authHandler := handlers.NewAuthHandler(
		db.NewUserRepository(database),
		auth.NewService(testSecret, time.Hour),
		bcrypt.MinCost, // fastest hashing — production uses BCRYPT_COST
	)
	return &app{
		router:   handlers.NewRouter(quiet, database, verifier, authHandler),
		database: database,
		verifier: verifier,
	}
}

// post sends a JSON POST request and returns the recorded response.
func (a *app) post(path string, body any, token string) *httptest.ResponseRecorder {
	var buf bytes.Buffer
	if s, ok := body.(string); ok {
		buf.WriteString(s) // raw text, for the "broken JSON" test
	} else if body != nil {
		json.NewEncoder(&buf).Encode(body)
	}
	req := httptest.NewRequest(http.MethodPost, path, &buf)
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	rec := httptest.NewRecorder()
	a.router.ServeHTTP(rec, req)
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

type credentials struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

var ali = credentials{Email: "ali@example.com", Password: "correct-horse"}

const (
	register = "/api/v1/auth/register"
	login    = "/api/v1/auth/login"
	logout   = "/api/v1/auth/logout"
)

// ── Register ─────────────────────────────────────────────────

func TestRegisterCreatesAUserAndReturnsAToken(t *testing.T) {
	a := newApp(t)

	rec := a.post(register, ali, "")

	if rec.Code != http.StatusCreated {
		t.Fatalf("status = %d, want 201 (%s)", rec.Code, rec.Body.String())
	}
	body := decode[models.AuthResponse](t, rec)
	if body.User.ID == "" || body.User.Email != ali.Email {
		t.Errorf("user = %+v, want an id and email %s", body.User, ali.Email)
	}

	// The token must be one that EVERY service accepts (shared verifier),
	// and it must name this user.
	claims, err := a.verifier.ValidateToken(body.Token)
	if err != nil {
		t.Fatalf("the shared verifier rejected the token: %v", err)
	}
	if claims.UserID != body.User.ID {
		t.Errorf("token user_id = %q, want %q", claims.UserID, body.User.ID)
	}
}

func TestPasswordIsStoredHashedAndNeverSentBack(t *testing.T) {
	a := newApp(t)

	rec := a.post(register, ali, "")

	if bytes.Contains(rec.Body.Bytes(), []byte("password")) {
		t.Errorf("the response mentions a password: %s", rec.Body.String())
	}
	var stored string
	err := a.database.Pool.QueryRow(context.Background(),
		"SELECT password_hash FROM users WHERE email = $1", ali.Email).Scan(&stored)
	if err != nil {
		t.Fatalf("read the stored hash: %v", err)
	}
	if stored == ali.Password {
		t.Fatal("the password is stored as plain text")
	}
	if err := bcrypt.CompareHashAndPassword([]byte(stored), []byte(ali.Password)); err != nil {
		t.Errorf("the stored hash doesn't match the password: %v", err)
	}
}

func TestRegisterTheSameEmailTwiceIs409(t *testing.T) {
	a := newApp(t)
	a.post(register, ali, "")

	// Same account, typed differently: must still count as taken.
	again := credentials{Email: "  ALI@Example.com ", Password: "another-password"}
	wantError(t, a.post(register, again, ""), http.StatusConflict, "email already registered")
}

func TestRegisterRejectsBadInput(t *testing.T) {
	a := newApp(t)

	tests := []struct {
		name    string
		body    any
		message string
	}{
		{"broken JSON", `{"email":`, "invalid request body"},
		{"no email", credentials{Password: "long-enough"}, "email is required"},
		{"not an email", credentials{Email: "ali", Password: "long-enough"}, `"ali" is not a valid email`},
		{"short password", credentials{Email: "ali@example.com", Password: "short"}, "password must be at least 8 characters"},
		{"very long password", credentials{Email: "ali@example.com", Password: string(make([]byte, 73))}, "password must be 72 characters or fewer"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			wantError(t, a.post(register, tt.body, ""), http.StatusBadRequest, tt.message)
		})
	}
}

// ── Login ────────────────────────────────────────────────────

func TestLoginReturnsATokenForTheSameUser(t *testing.T) {
	a := newApp(t)
	registered := decode[models.AuthResponse](t, a.post(register, ali, ""))

	// Typed with capitals and spaces: still the same account.
	rec := a.post(login, credentials{Email: " Ali@Example.com", Password: ali.Password}, "")

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200 (%s)", rec.Code, rec.Body.String())
	}
	body := decode[models.AuthResponse](t, rec)
	claims, err := a.verifier.ValidateToken(body.Token)
	if err != nil {
		t.Fatalf("the shared verifier rejected the token: %v", err)
	}
	// The user id never changes: it is what todos and the agent's memory hang on.
	if claims.UserID != registered.User.ID {
		t.Errorf("token user_id = %q, want %q", claims.UserID, registered.User.ID)
	}
}

// A wrong password and an unknown email must look exactly the same, so
// nobody can find out which emails have an account.
func TestLoginFailuresLookTheSame(t *testing.T) {
	a := newApp(t)
	a.post(register, ali, "")

	wrongPassword := a.post(login, credentials{Email: ali.Email, Password: "wrong-password"}, "")
	unknownEmail := a.post(login, credentials{Email: "nobody@example.com", Password: ali.Password}, "")

	wantError(t, wrongPassword, http.StatusUnauthorized, "invalid email or password")
	wantError(t, unknownEmail, http.StatusUnauthorized, "invalid email or password")
}

func TestLoginNeedsEmailAndPassword(t *testing.T) {
	a := newApp(t)
	wantError(t, a.post(login, credentials{Email: ali.Email}, ""), http.StatusBadRequest, "email and password are required")
}

// ── Logout ───────────────────────────────────────────────────

func TestLogoutNeedsAValidToken(t *testing.T) {
	a := newApp(t)
	token := decode[models.AuthResponse](t, a.post(register, ali, "")).Token

	if rec := a.post(logout, nil, token); rec.Code != http.StatusOK {
		t.Errorf("logout with a token: status = %d, want 200", rec.Code)
	}
	wantError(t, a.post(logout, nil, ""), http.StatusUnauthorized, "missing authorization header")
	wantError(t, a.post(logout, nil, "not-a-token"), http.StatusUnauthorized, "token is invalid")
}

// ── Health ───────────────────────────────────────────────────

func TestHealthEndpoints(t *testing.T) {
	a := newApp(t)
	for _, path := range []string{"/health", "/health/ready"} {
		rec := httptest.NewRecorder()
		a.router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, path, nil))
		if rec.Code != http.StatusOK {
			t.Errorf("GET %s: status = %d, want 200 (%s)", path, rec.Code, rec.Body.String())
		}
	}
}
