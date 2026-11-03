// ============================================================
// lib/types.ts — the API contract, written as TypeScript types.
//
// These mirror the Go structs in services/api/internal/models/
// (and ChatRequest/ChatResponse in handlers/agent_handler.go).
// Field names match the `json:"..."` tags, so a JSON response can
// be used directly as one of these types.
//
// Rule 2 in docs/ROADMAP.md: web never imports Go code. The only
// link between the two services is this HTTP contract — if a Go
// struct changes, update the matching type here.
// ============================================================

// ── Users & auth ─────────────────────────────────────────────

// models.User (PasswordHash is json:"-", so it never appears)
export type User = {
  id: string;
  email: string;
  created_at: string; // ISO 8601 timestamp (Go time.Time)
  updated_at: string;
};

// models.RegisterRequest / models.LoginRequest
export type Credentials = {
  email: string;
  password: string;
};

// models.AuthResponse — returned by register and login
export type AuthResponse = {
  token: string; // JWT, sent back as "Authorization: Bearer <token>"
  user: User;
};

// ── Todos ────────────────────────────────────────────────────

// models.Priority
export type Priority = "low" | "medium" | "high";

// models.Todo
export type Todo = {
  id: string;
  user_id: string;
  title: string;
  description?: string; // omitempty — missing when empty
  priority: Priority;
  done: boolean;
  done_at?: string; // omitempty — only set once done
  created_at: string;
  updated_at: string;
};

// models.CreateTodoRequest (priority defaults to "medium" on the server)
export type CreateTodoRequest = {
  title: string;
  description?: string;
  priority?: Priority;
};

// models.UpdateTodoRequest — only the fields you send are changed
export type UpdateTodoRequest = {
  title?: string;
  description?: string;
  priority?: Priority;
  done?: boolean;
};

// ── Agent ────────────────────────────────────────────────────

// handlers.ChatResponse
export type ChatResponse = {
  reply: string;
};

// ── Errors ───────────────────────────────────────────────────

// models.ErrorResponse — the body of every 4xx/5xx from the API
export type ErrorResponse = {
  error: string;
  request_id?: string; // matches request_id in the api's logs
};
