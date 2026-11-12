// Package auth CREATES JWT tokens — the part only the auth service does.
//
// WHY A SEPARATE PACKAGE?
// JWT logic is neither HTTP (handlers) nor database (db).
// It is a pure service — takes a user ID, returns a token string.
//
// WHERE IS VALIDATION?
// Checking a token is needed by every service, so it lives in the
// shared library: libs/go/jwtauth (Verifier + the HTTP middleware).
// Creating a token happens ONLY here, in the auth service — it is the
// one service that may say "this person logged in". The Claims type is
// shared, so the token we write here is exactly what jwtauth reads.
package auth

import (
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"

	"github.com/MirajHoque/todo-microservice/libs/go/jwtauth"
)

// Service handles JWT creation.
type Service struct {
	secret []byte
	expiry time.Duration
}

// NewService creates a JWT service.
// secret is your JWT_SECRET from .env.
// expiry is how long tokens are valid (e.g. 24h).
func NewService(secret string, expiry time.Duration) *Service {
	return &Service{
		secret: []byte(secret),
		expiry: expiry,
	}
}

// CreateToken generates a signed JWT token for the given user ID.
// Called by the login and register handlers after password verification.
//
// The token payload contains:
//   - user_id: who this token belongs to
//   - exp:     when it expires (now + expiry duration)
//   - iat:     when it was issued (now)
func (s *Service) CreateToken(userID string) (string, error) {
	now := time.Now()

	claims := jwtauth.Claims{
		UserID: userID,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(now.Add(s.expiry)),
			IssuedAt:  jwt.NewNumericDate(now),
			Issuer:    "todo-app",
		},
	}

	// jwt.NewWithClaims creates the token with HS256 signing method.
	// SignedString(secret) produces the final token string.
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := token.SignedString(s.secret)
	if err != nil {
		return "", fmt.Errorf("auth: sign token: %w", err)
	}

	return signed, nil
}
