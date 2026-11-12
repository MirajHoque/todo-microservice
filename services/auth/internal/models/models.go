// Package models defines the auth service's domain types: the User,
// and the JSON bodies of its endpoints.
//
// These types belong to THIS service only. Other services never import
// them (ROADMAP rule 2) — the only thing they learn about a user is the
// `user_id` inside the JWT.
//
// Rules for this package:
//   - No database logic here. Models describe the DOMAIN, not the DB schema.
//   - Validation lives here because it belongs to the domain, not to a layer.
package models

import (
	"fmt"
	"strings"
	"time"
)

// ---- User -------------------------------------------------------------------

// User represents an account.
// Struct tags (`json:"..."`) control the key names in the JSON output.
type User struct {
	ID           string    `json:"id"`
	Email        string    `json:"email"`
	PasswordHash string    `json:"-"` // never serialise the hash
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

// NormalizeEmail makes "  Ali@Example.com " and "ali@example.com" the
// same account. Used by register AND login, so they always agree.
func NormalizeEmail(email string) string {
	return strings.TrimSpace(strings.ToLower(email))
}

// ---- Request / Response types -----------------------------------------------
// These are the HTTP layer types — separate from the domain model on purpose.
// If the API contract changes, only these change, not the domain model.

// RegisterRequest is the body expected on POST /api/v1/auth/register.
type RegisterRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// Validate cleans up the email and checks the rules for a new account.
func (r *RegisterRequest) Validate() error {
	r.Email = NormalizeEmail(r.Email)
	if r.Email == "" {
		return fmt.Errorf("email is required")
	}
	if !strings.Contains(r.Email, "@") {
		return fmt.Errorf("%q is not a valid email", r.Email)
	}
	if len(r.Password) < 8 {
		return fmt.Errorf("password must be at least 8 characters")
	}
	// bcrypt only looks at the first 72 bytes of a password; Go's bcrypt
	// returns an error for longer ones. Say so clearly instead of a 500.
	if len(r.Password) > 72 {
		return fmt.Errorf("password must be 72 characters or fewer")
	}
	return nil
}

// LoginRequest is the body expected on POST /api/v1/auth/login.
type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// AuthResponse is returned after a successful login or register.
type AuthResponse struct {
	Token string `json:"token"`
	User  *User  `json:"user"`
}
