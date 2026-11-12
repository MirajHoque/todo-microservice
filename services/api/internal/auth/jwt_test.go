// The contract between the two halves of JWT:
// a token CREATED here must be ACCEPTED by the shared library
// (libs/go/jwtauth), which is what every other Go service uses.
package auth

import (
	"testing"
	"time"

	"github.com/MirajHoque/todo-microservice/libs/go/jwtauth"
)

const secret = "test-secret-at-least-32-characters-long"

func TestCreatedTokenIsAcceptedByTheSharedVerifier(t *testing.T) {
	token, err := NewService(secret, time.Hour).CreateToken("user-1")
	if err != nil {
		t.Fatalf("create token: %v", err)
	}

	claims, err := jwtauth.NewVerifier(secret).ValidateToken(token)
	if err != nil {
		t.Fatalf("verifier rejected our own token: %v", err)
	}
	if claims.UserID != "user-1" {
		t.Errorf("user id = %q, want user-1", claims.UserID)
	}
	if claims.Issuer != "todo-app" {
		t.Errorf("issuer = %q, want todo-app", claims.Issuer)
	}
}

func TestAServiceWithAnotherSecretRejectsTheToken(t *testing.T) {
	token, err := NewService(secret, time.Hour).CreateToken("user-1")
	if err != nil {
		t.Fatalf("create token: %v", err)
	}
	if _, err := jwtauth.NewVerifier("a-different-secret-0123456789abcdef").ValidateToken(token); err == nil {
		t.Error("a verifier with a different JWT_SECRET accepted the token")
	}
}
