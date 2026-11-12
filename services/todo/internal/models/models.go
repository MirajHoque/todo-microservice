// Package models defines the core domain types for the todo application.
/*
 domain types" it just means "types that describe the real world problem"
 — Todos, not HTTP or SQL.
*/

// models.go describes what things are (Todo) and what makes them valid.
// It does not care how they travel over the internet or how they are stored in a database.

// Rules for this package:
//   - No database logic here. Models describe the DOMAIN, not the DB schema.
//   - No HTTP logic here. Models are not JSON request/response types.
//   - Validation lives here because it belongs to the domain, not to a layer.
package models

import (
	"fmt"
	"strings"
	"time"
)

// (There is no User type here: users belong to services/auth. This
// service only knows a user as the `user_id` string inside the JWT.)

// ---- Todo -------------------------------------------------------------------

// A struct field is: name, type, struct tag.
// Struct tags are metadata that tell the encoder/decoder how to name or handle fields.
//
//	tags only control the keys

// Priority controls how urgent a todo item is.
// Custom Type, replicate Enum in C#/Java
type Priority string

const (
	PriorityLow    Priority = "low"
	PriorityMedium Priority = "medium"
	PriorityHigh   Priority = "high"
)

// Todo represents a single task owned by a user.
type Todo struct {
	ID          string     `json:"id"`
	UserID      string     `json:"user_id"`
	Title       string     `json:"title"`
	Description string     `json:"description,omitempty"`
	Priority    Priority   `json:"priority"`
	Done        bool       `json:"done"`
	DoneAt      *time.Time `json:"done_at,omitempty"`
	CreatedAt   time.Time  `json:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
}

// Validate checks that a Todo is internally consistent.
// The messages are sent to the client as they are (400 Bad Request).
func (t *Todo) Validate() error {
	t.Title = strings.TrimSpace(t.Title)
	if t.Title == "" {
		return fmt.Errorf("title is required")
	}
	if len(t.Title) > 255 {
		return fmt.Errorf("title must be 255 characters or fewer")
	}
	if t.Priority == "" {
		t.Priority = PriorityMedium
	}
	return t.Priority.Validate()
}

// Validate checks that p is one of the three known priorities.
func (p Priority) Validate() error {
	switch p {
	case PriorityLow, PriorityMedium, PriorityHigh:
		return nil
	default:
		return fmt.Errorf("invalid priority %q, must be low, medium, or high", string(p))
	}
}

// Complete marks a todo as done and records the timestamp.
func (t *Todo) Complete() {
	now := time.Now().UTC()
	t.Done = true
	t.DoneAt = &now
	t.UpdatedAt = now
}

// ---- Request / Response types -----------------------------------------------
// These are the HTTP layer types — separate from domain models on purpose.
// If the API contract changes, only these change, not the domain model.

// CreateTodoRequest is the body expected on POST /api/v1/todos.
type CreateTodoRequest struct {
	Title       string   `json:"title"`
	Description string   `json:"description"`
	Priority    Priority `json:"priority"`
}

func (r *CreateTodoRequest) Validate() error {
	r.Title = strings.TrimSpace(r.Title)
	if r.Title == "" {
		return fmt.Errorf("title is required")
	}
	if len(r.Title) > 255 {
		return fmt.Errorf("title must be 255 characters or fewer")
	}
	// Empty is fine: the repository fills in "medium".
	if r.Priority != "" {
		return r.Priority.Validate()
	}
	return nil
}

// UpdateTodoRequest is the body expected on PATCH /api/v1/todos/:id.
type UpdateTodoRequest struct {
	Title       *string   `json:"title,omitempty"`
	Description *string   `json:"description,omitempty"`
	Priority    *Priority `json:"priority,omitempty"`
	Done        *bool     `json:"done,omitempty"`
}

// ErrorResponse is the standard error envelope returned on 4xx/5xx.
type ErrorResponse struct {
	Error     string `json:"error"`
	RequestID string `json:"request_id,omitempty"`
}
