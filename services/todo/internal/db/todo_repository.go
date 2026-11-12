// todo_repository.go — all SQL for the todos table.
//
// REPOSITORY PATTERN
// A repository is a Go struct that owns all database queries for one
// table. Handlers call its methods instead of writing SQL themselves:
//   - One struct that owns all queries for this table
//   - Each method does one thing
//   - SQL errors are converted to sentinel errors where needed
//
// The `todos` table has exactly ONE owner: this service (ROADMAP rule
// 3). The agent changes todos through this service's HTTP API.
//
// The connection pool comes from the shared library (libs/go/postgres);
// the SQL stays here, because it knows about todos.
package db

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/MirajHoque/todo-microservice/libs/go/postgres"
	"github.com/MirajHoque/todo-microservice/services/todo/internal/models"
)

// TodoRepository handles all database operations for the todos table.
type TodoRepository struct {
	db *postgres.DB
}

// NewTodoRepository creates a TodoRepository.
func NewTodoRepository(db *postgres.DB) *TodoRepository {
	return &TodoRepository{db: db}
}

// isUUID reports whether id looks like a todo id. An id that isn't a
// UUID can't belong to any todo — callers answer "not found" instead
// of sending it to Postgres, which would fail with a type error (a 500).
func isUUID(id string) bool {
	return uuid.Validate(id) == nil
}

// Create inserts a new todo for the given user.
// The ID, created_at, updated_at are filled by PostgreSQL — not by Go.
func (r *TodoRepository) Create(ctx context.Context, userID string, req *models.CreateTodoRequest) (*models.Todo, error) {
	// Default priority to medium if not set
	priority := req.Priority
	if priority == "" {
		priority = models.PriorityMedium
	}

	todo := &models.Todo{}

	err := r.db.Pool.QueryRow(ctx, `
		INSERT INTO todos (user_id, title, description, priority)
		VALUES ($1, $2, $3, $4)
		RETURNING id, user_id, title, description, priority, done, done_at, created_at, updated_at
	`, userID, req.Title, req.Description, priority).Scan(
		&todo.ID,
		&todo.UserID,
		&todo.Title,
		&todo.Description,
		&todo.Priority,
		&todo.Done,
		&todo.DoneAt,
		&todo.CreatedAt,
		&todo.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("todo repo: create: %w", err)
	}

	return todo, nil
}

// ListByUser returns all todos for a user, newest first.
// Only returns todos belonging to that user — never another user's todos.
func (r *TodoRepository) ListByUser(ctx context.Context, userID string) ([]*models.Todo, error) {
	rows, err := r.db.Pool.Query(ctx, `
		SELECT id, user_id, title, description, priority, done, done_at, created_at, updated_at
		FROM todos
		WHERE user_id = $1
		ORDER BY created_at DESC
	`, userID)
	if err != nil {
		return nil, fmt.Errorf("todo repo: list: %w", err)
	}
	defer rows.Close()

	var todos []*models.Todo
	for rows.Next() {
		todo := &models.Todo{}
		if err := rows.Scan(
			&todo.ID,
			&todo.UserID,
			&todo.Title,
			&todo.Description,
			&todo.Priority,
			&todo.Done,
			&todo.DoneAt,
			&todo.CreatedAt,
			&todo.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("todo repo: list scan: %w", err)
		}
		todos = append(todos, todo)
	}

	// rows.Err() catches any error that occurred during iteration.
	// Always check this after iterating pgx rows.
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("todo repo: list rows: %w", err)
	}

	// Return empty slice instead of nil — cleaner JSON response ([])
	if todos == nil {
		todos = []*models.Todo{}
	}

	return todos, nil
}

// GetByID fetches a single todo by ID.
// Also checks user_id — a user cannot fetch another user's todo.
// Returns ErrTodoNotFound if the todo doesn't exist OR belongs to someone else.
func (r *TodoRepository) GetByID(ctx context.Context, id, userID string) (*models.Todo, error) {
	if !isUUID(id) {
		return nil, ErrTodoNotFound
	}
	todo := &models.Todo{}

	err := r.db.Pool.QueryRow(ctx, `
		SELECT id, user_id, title, description, priority, done, done_at, created_at, updated_at
		FROM todos
		WHERE id = $1 AND user_id = $2
	`, id, userID).Scan(
		&todo.ID,
		&todo.UserID,
		&todo.Title,
		&todo.Description,
		&todo.Priority,
		&todo.Done,
		&todo.DoneAt,
		&todo.CreatedAt,
		&todo.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrTodoNotFound
		}
		return nil, fmt.Errorf("todo repo: get by id: %w", err)
	}

	return todo, nil
}

// Update modifies an existing todo.
// Only updates fields that are provided in the request (partial update).
// Also verifies the todo belongs to userID — prevents users editing others' todos.
func (r *TodoRepository) Update(ctx context.Context, id, userID string, req *models.UpdateTodoRequest) (*models.Todo, error) {
	// First verify it exists and belongs to this user
	todo, err := r.GetByID(ctx, id, userID)
	if err != nil {
		return nil, err
	}

	// Apply only the fields that were provided in the request.
	// Pointer fields — nil means "not provided, keep current value".
	if req.Title != nil {
		todo.Title = *req.Title
	}
	if req.Description != nil {
		todo.Description = *req.Description
	}
	if req.Priority != nil {
		todo.Priority = *req.Priority
	}
	if req.Done != nil {
		todo.Done = *req.Done
		if *req.Done {
			todo.Complete() // sets DoneAt timestamp
		} else {
			todo.DoneAt = nil // uncompleting a todo clears DoneAt
		}
	}

	// Validate the updated todo. A broken rule (empty title, unknown
	// priority) is the CALLER's mistake: wrap it in ErrInvalidTodo so
	// the handler can answer 400 instead of 500.
	if err := todo.Validate(); err != nil {
		return nil, fmt.Errorf("%w: %w", ErrInvalidTodo, err)
	}

	err = r.db.Pool.QueryRow(ctx, `
		UPDATE todos
		SET title = $1, description = $2, priority = $3, done = $4, done_at = $5
		WHERE id = $6 AND user_id = $7
		RETURNING id, user_id, title, description, priority, done, done_at, created_at, updated_at
	`,
		todo.Title,
		todo.Description,
		todo.Priority,
		todo.Done,
		todo.DoneAt,
		id,
		userID,
	).Scan(
		&todo.ID,
		&todo.UserID,
		&todo.Title,
		&todo.Description,
		&todo.Priority,
		&todo.Done,
		&todo.DoneAt,
		&todo.CreatedAt,
		&todo.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("todo repo: update: %w", err)
	}

	return todo, nil
}

// Delete removes a todo permanently.
// Checks user_id — a user cannot delete another user's todo.
// Returns ErrTodoNotFound if the todo doesn't exist or belongs to someone else.
func (r *TodoRepository) Delete(ctx context.Context, id, userID string) error {
	if !isUUID(id) {
		return ErrTodoNotFound
	}
	result, err := r.db.Pool.Exec(ctx, `
		DELETE FROM todos
		WHERE id = $1 AND user_id = $2
	`, id, userID)
	if err != nil {
		return fmt.Errorf("todo repo: delete: %w", err)
	}

	// RowsAffected tells us if any row was actually deleted.
	// If 0 — either the todo doesn't exist or belongs to another user.
	if result.RowsAffected() == 0 {
		return ErrTodoNotFound
	}

	return nil
}

// ---- Sentinel errors --------------------------------------------------------

// ErrTodoNotFound is returned when a todo lookup finds no matching row
// or when the todo belongs to a different user.
var ErrTodoNotFound = errors.New("todo not found")

// ErrInvalidTodo is returned when an update would break a rule of a
// todo (see models.Todo.Validate). The wrapped error says which rule.
var ErrInvalidTodo = errors.New("invalid todo")
