// ============================================================
// lib/api.ts — one small function per API endpoint.
//
// Pages call these instead of using fetch() directly, so the
// details live in one place:
//   - the base path /api/v1 (proxy.ts forwards /api/v1/agent/...
//     to the Python agent, everything else to the Go api)
//   - JSON encoding/decoding
//   - attaching the JWT ("Authorization: Bearer <token>")
//   - turning error responses into an ApiError
//
// Usage from a page:
//   const todos = await listTodos();
//   try { await login(email, pw) } catch (e) {
//     if (e instanceof ApiError && e.status === 401) ...
//   }
// ============================================================

import { getToken } from "./session";
import type {
  AuthResponse,
  ChatResponse,
  CreateTodoRequest,
  ErrorResponse,
  Todo,
  UpdateTodoRequest,
} from "./types";

// Relative URL: the browser sends it to web (localhost:3000), and
// web forwards it to the api. The browser never needs the api's address.
const BASE = "/api/v1";

// ApiError is thrown for every non-2xx response.
// status is the HTTP code (401 = not logged in / token expired,
// 404 = not found, ...), message is the API's "error" field.
export class ApiError extends Error {
  status: number;
  requestId?: string;

  constructor(status: number, message: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
  }
}

// request is the one place that actually calls fetch().
async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    // Both services send {"error": "...", "request_id": "..."}. If a
    // service is down, web's proxy answers 500 with plain text instead —
    // so no JSON body + a 5xx means "that service did not answer".
    const err = (await res.json().catch(() => null)) as ErrorResponse | null;
    const service = path.startsWith("/agent") ? "agent" : "api";
    const message =
      err?.error ??
      (res.status >= 500 ? `Cannot reach the ${service}. Is it running?` : res.statusText);
    throw new ApiError(res.status, message, err?.request_id);
  }

  // 204 No Content (e.g. delete) has no body to parse.
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ── Auth ─────────────────────────────────────────────────────

// POST /auth/register → 201 { token, user } (409 if email is taken)
export function register(email: string, password: string): Promise<AuthResponse> {
  return request("POST", "/auth/register", { email, password });
}

// POST /auth/login → 200 { token, user } (401 if wrong email/password)
export function login(email: string, password: string): Promise<AuthResponse> {
  return request("POST", "/auth/login", { email, password });
}

// POST /auth/logout → 200. A JWT can't be revoked, so this only logs
// the logout; the caller must also clearSession() in the browser.
export async function logout(): Promise<void> {
  await request("POST", "/auth/logout");
}

// ── Todos (all need a token) ─────────────────────────────────

// GET /todos → 200 [todos], newest first
export async function listTodos(): Promise<Todo[]> {
  return (await request<Todo[] | null>("GET", "/todos")) ?? [];
}

// POST /todos → 201 todo
export function createTodo(input: CreateTodoRequest): Promise<Todo> {
  return request("POST", "/todos", input);
}

// PATCH /todos/{id} → 200 todo (only the fields sent are changed)
export function updateTodo(id: string, changes: UpdateTodoRequest): Promise<Todo> {
  return request("PATCH", `/todos/${encodeURIComponent(id)}`, changes);
}

// DELETE /todos/{id} → 204 (no body)
export function deleteTodo(id: string): Promise<void> {
  return request("DELETE", `/todos/${encodeURIComponent(id)}`);
}

// ── Agent (needs a token) — answered by the Python agent ─────

// POST /agent/chat → 200 { reply }
export async function chat(message: string): Promise<string> {
  const res = await request<ChatResponse>("POST", "/agent/chat", { message });
  return res.reply;
}

// DELETE /agent/conversation → 204. Forgets this user's chat history
// (the agent's memory in agent_db), so the next chat starts fresh.
export function clearConversation(): Promise<void> {
  return request("DELETE", "/agent/conversation");
}
