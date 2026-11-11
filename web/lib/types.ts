// ============================================================
// lib/types.ts — the API contract, written as TypeScript types.
//
// These mirror the Go structs in services/api/internal/models/
// and the agent's Pydantic models in services/agent/src/agent/routes/.
// Field names match the JSON field names, so a JSON response can be
// used directly as one of these types.
//
// Rule 2 in docs/ROADMAP.md: web never imports another service's
// code. The only link is this HTTP contract — if a Go struct or a
// Pydantic model changes, update the matching type here.
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

// ── Agent (the Python service: services/agent) ───────────────

// A deletion the agent proposed. Nothing is deleted until the user
// presses Confirm (step 2i.1) — routes/chat.py PendingAction.
export type PendingAction = {
  id: string;
  kind: "delete_todos";
  todos: { id: string; title: string }[];
  expires_at: string; // the buttons stop working after this
};

// routes/chat.py ChatResponse — pending_action only when there is one
export type ChatResponse = {
  reply: string;
  pending_action?: PendingAction;
};

// routes/actions.py ActionResponse — after Confirm / Cancel
export type ActionResponse = {
  reply: string;
};

// ── Errors ───────────────────────────────────────────────────

// models.ErrorResponse — the body of every 4xx/5xx from the API
export type ErrorResponse = {
  error: string;
  request_id?: string; // matches request_id in the api's logs
};
