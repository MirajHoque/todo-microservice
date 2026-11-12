// Tests for the shared JWT check.
//
// The tests sign their own tokens with the jwt library (this package
// can't create tokens — on purpose), then ask the Verifier about them.
package jwtauth

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"

	"github.com/MirajHoque/todo-microservice/libs/go/middleware"
	"github.com/MirajHoque/todo-microservice/libs/go/respond"
)

const secret = "test-secret-at-least-32-characters-long"

// sign makes a token the way the auth service does.
func sign(t *testing.T, method jwt.SigningMethod, key any, userID string, expiresIn time.Duration) string {
	t.Helper()
	now := time.Now()
	claims := Claims{
		UserID: userID,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(now.Add(expiresIn)),
			IssuedAt:  jwt.NewNumericDate(now),
			Issuer:    "todo-app",
		},
	}
	token, err := jwt.NewWithClaims(method, claims).SignedString(key)
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return token
}

func TestValidateToken(t *testing.T) {
	verifier := NewVerifier(secret)

	t.Run("a good token gives the user id", func(t *testing.T) {
		token := sign(t, jwt.SigningMethodHS256, []byte(secret), "user-1", time.Hour)
		claims, err := verifier.ValidateToken(token)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if claims.UserID != "user-1" {
			t.Errorf("user id = %q, want user-1", claims.UserID)
		}
	})

	t.Run("an expired token is rejected", func(t *testing.T) {
		token := sign(t, jwt.SigningMethodHS256, []byte(secret), "user-1", -time.Minute)
		if _, err := verifier.ValidateToken(token); !errors.Is(err, ErrTokenExpired) {
			t.Errorf("error = %v, want ErrTokenExpired", err)
		}
	})

	t.Run("a token signed with another secret is rejected", func(t *testing.T) {
		token := sign(t, jwt.SigningMethodHS256, []byte("someone-else's-secret-0123456789"), "user-1", time.Hour)
		if _, err := verifier.ValidateToken(token); !errors.Is(err, ErrTokenInvalid) {
			t.Errorf("error = %v, want ErrTokenInvalid", err)
		}
	})

	// The "alg: none" attack: a token with NO signature that claims to be valid.
	t.Run("an unsigned token is rejected", func(t *testing.T) {
		token := sign(t, jwt.SigningMethodNone, jwt.UnsafeAllowNoneSignatureType, "user-1", time.Hour)
		if _, err := verifier.ValidateToken(token); !errors.Is(err, ErrTokenInvalid) {
			t.Errorf("error = %v, want ErrTokenInvalid", err)
		}
	})

	t.Run("garbage is rejected", func(t *testing.T) {
		if _, err := verifier.ValidateToken("not-a-token"); !errors.Is(err, ErrTokenInvalid) {
			t.Errorf("error = %v, want ErrTokenInvalid", err)
		}
	})
}

func TestMiddleware(t *testing.T) {
	verifier := NewVerifier(secret)
	good := sign(t, jwt.SigningMethodHS256, []byte(secret), "user-1", time.Hour)

	// The "handler behind the door": remembers who the middleware let in.
	var sawUser string
	var called bool
	// RequestID runs first, as in a real service: the 401 needs the id.
	handler := middleware.RequestID(verifier.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		sawUser = middleware.GetUserID(r.Context())
	})))

	tests := []struct {
		name       string
		header     string // the Authorization header; "" = not sent
		wantStatus int
		wantUser   string
	}{
		{"good token reaches the handler", "Bearer " + good, http.StatusOK, "user-1"},
		{"bearer in lower case is fine", "bearer " + good, http.StatusOK, "user-1"},
		{"no header", "", http.StatusUnauthorized, ""},
		{"not a Bearer header", "Basic abc", http.StatusUnauthorized, ""},
		{"bad token", "Bearer nope", http.StatusUnauthorized, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			called, sawUser = false, ""
			req := httptest.NewRequest(http.MethodGet, "/todos", nil)
			req.Header.Set("X-Request-ID", "req-1")
			if tt.header != "" {
				req.Header.Set("Authorization", tt.header)
			}
			rec := httptest.NewRecorder()

			handler.ServeHTTP(rec, req)

			if rec.Code != tt.wantStatus {
				t.Errorf("status = %d, want %d", rec.Code, tt.wantStatus)
			}
			// A 401 is JSON with the request id, like every other error.
			if tt.wantStatus == http.StatusUnauthorized {
				var body respond.ErrorBody
				if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
					t.Fatalf("401 body is not JSON: %v\n%s", err, rec.Body.String())
				}
				if body.Error == "" || body.RequestID != "req-1" {
					t.Errorf("401 body = %+v, want an error and request_id req-1", body)
				}
			}
			if sawUser != tt.wantUser {
				t.Errorf("user id = %q, want %q", sawUser, tt.wantUser)
			}
			// On 401 the handler must never run.
			if wantCalled := tt.wantStatus == http.StatusOK; called != wantCalled {
				t.Errorf("handler called = %v, want %v", called, wantCalled)
			}
		})
	}
}
