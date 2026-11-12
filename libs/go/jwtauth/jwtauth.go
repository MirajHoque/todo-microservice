// Package jwtauth CHECKS JWT tokens. It never creates them.
//
// SHARED CODE (libs/go): every Go service that has protected routes
// uses this package to answer one question: "is this token real, and
// which user does it belong to?"
//
// WHY ONLY CHECKING?
// Creating a token ("this person just logged in") is the auth
// service's job alone, so that code stays inside the auth service
// (today: services/api/internal/auth). Checking a token is needed by
// every service, so it lives here.
//
//	auth service ── CreateToken ──▶ token ──▶ browser
//	browser ── token ──▶ any service ── Verifier.ValidateToken ──▶ user id
//
// Both sides must agree on two things, which is why they are defined
// here, once:
//   - the Claims (what is written inside the token)
//   - the signing method (HS256 with the shared JWT_SECRET)
//
// The Python agent checks the same tokens with its own code
// (services/agent/src/agent/auth.py) — the contract between services
// is the token format, not this Go package.
package jwtauth

import (
	"errors"
	"fmt"

	"github.com/golang-jwt/jwt/v5"
)

// Claims defines what we store inside the JWT payload.
// jwt.RegisteredClaims adds standard fields like ExpiresAt, IssuedAt.
// We add our own UserID field on top.
type Claims struct {
	UserID string `json:"user_id"`
	jwt.RegisteredClaims
}

// Verifier checks tokens that were signed with one secret.
type Verifier struct {
	secret []byte
}

// NewVerifier creates a Verifier.
// secret is the JWT_SECRET from .env — the same value the auth service signs with.
func NewVerifier(secret string) *Verifier {
	return &Verifier{secret: []byte(secret)}
}

// ValidateToken parses and validates a JWT token string.
// Returns the claims (including user_id) if valid.
// Returns an error if:
//   - the token is malformed
//   - the signature doesn't match (tampered, or signed with another secret)
//   - the token has expired
func (v *Verifier) ValidateToken(tokenString string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(
		tokenString,
		&Claims{},
		// This function is called by the JWT library to get the signing key.
		// We verify the algorithm matches what we use (HS256) to prevent
		// algorithm confusion attacks where an attacker sends "alg: none".
		func(token *jwt.Token) (any, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("jwtauth: unexpected signing method: %v", token.Header["alg"])
			}
			return v.secret, nil
		},
	)

	if err != nil {
		// Convert jwt library errors to our own descriptive errors.
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, ErrTokenExpired
		}
		return nil, ErrTokenInvalid
	}

	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid {
		return nil, ErrTokenInvalid
	}

	return claims, nil
}

// ---- Sentinel errors --------------------------------------------------------

// ErrTokenInvalid is returned when a token cannot be parsed or verified.
var ErrTokenInvalid = errors.New("token is invalid")

// ErrTokenExpired is returned when a token's expiry time has passed.
var ErrTokenExpired = errors.New("token has expired")
