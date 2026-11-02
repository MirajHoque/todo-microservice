// ============================================================
// app/todos/page.tsx — the /todos page: your todo list.
//
// Every action is one call from lib/api.ts:
//   load    → listTodos()   GET    /api/v1/todos
//   add     → createTodo()  POST   /api/v1/todos
//   tick    → updateTodo()  PATCH  /api/v1/todos/{id}
//   delete  → deleteTodo()  DELETE /api/v1/todos/{id}
//
// After add/tick/delete we update the list from the API's answer
// (the API returns the created/updated todo) instead of downloading
// the whole list again — one request per click.
//
// If the API answers 401, the token is missing or expired: forget
// it and go to /login.
// ============================================================

"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { TodoItem } from "@/components/todo-item";
import { ApiError, createTodo, deleteTodo, listTodos, logout, updateTodo } from "@/lib/api";
import { clearSession, getEmail, getToken } from "@/lib/session";
import type { Priority, Todo } from "@/lib/types";

// Read the email from localStorage (browser only; null on the server).
const noSubscribe = () => () => {};

export default function TodosPage() {
  const router = useRouter();
  const email = useSyncExternalStore(noSubscribe, getEmail, () => null);

  const [todos, setTodos] = useState<Todo[] | null>(null); // null = still loading
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null); // row with a request in flight

  // Add-todo form
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [adding, setAdding] = useState(false);

  // One place to handle any failed API call.
  const handleError = useCallback(
    (err: unknown, fallback: string) => {
      if (err instanceof ApiError && err.status === 401) {
        clearSession(); // token missing or expired
        router.replace("/login");
        return;
      }
      setError(err instanceof ApiError ? err.message : fallback);
    },
    [router],
  );

  // Load the list once when the page opens (or go to /login).
  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    listTodos()
      .then(setTodos)
      .catch((err) => handleError(err, "Could not load todos. Is the api running?"));
  }, [router, handleError]);

  async function handleAdd(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!title.trim()) return;
    setError(null);
    setAdding(true);
    try {
      const todo = await createTodo({ title: title.trim(), priority });
      setTodos((list) => [todo, ...(list ?? [])]); // newest first, like the API
      setTitle("");
      setPriority("medium");
    } catch (err) {
      handleError(err, "Could not add todo");
    } finally {
      setAdding(false);
    }
  }

  async function handleToggle(todo: Todo) {
    setError(null);
    setBusyId(todo.id);
    try {
      const updated = await updateTodo(todo.id, { done: !todo.done });
      setTodos((list) => list?.map((t) => (t.id === updated.id ? updated : t)) ?? null);
    } catch (err) {
      handleError(err, "Could not update todo");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(todo: Todo) {
    setError(null);
    setBusyId(todo.id);
    try {
      await deleteTodo(todo.id);
      setTodos((list) => list?.filter((t) => t.id !== todo.id) ?? null);
    } catch (err) {
      handleError(err, "Could not delete todo");
    } finally {
      setBusyId(null);
    }
  }

  async function handleLogout() {
    // Tell the API (it clears the agent's memory for this user), then
    // forget the token here. Logged out locally even if the call fails.
    await logout().catch(() => {});
    clearSession();
    router.push("/login");
  }

  const left = todos?.filter((t) => !t.done).length ?? 0;

  return (
    <div className="flex-1">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
          <span className="font-semibold">Todo</span>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-zinc-600">{email}</span>
            <button onClick={handleLogout} className="rounded-md px-3 py-1.5 hover:bg-zinc-100">
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-2xl p-4">
        <h1 className="mb-4 mt-4 text-2xl font-semibold">My Todos</h1>

        <form onSubmit={handleAdd} className="mb-4 flex gap-2">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What needs to be done?"
            maxLength={255} // same limit as the API (CreateTodoRequest.Validate)
            aria-label="New todo title"
            className="min-w-0 flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 focus:border-blue-600 focus:outline-none"
          />
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
            aria-label="Priority"
            className="rounded-md border border-zinc-300 bg-white px-2 py-2"
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
          <button
            type="submit"
            disabled={adding || !title.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {adding ? "Adding…" : "Add"}
          </button>
        </form>

        {error && (
          <p role="alert" className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        {todos === null && !error && <p className="py-8 text-center text-zinc-500">Loading…</p>}

        {todos?.length === 0 && (
          <div className="py-12 text-center text-zinc-500">
            <div className="mb-2 text-4xl">✓</div>
            <p className="font-medium text-zinc-700">All clear!</p>
            <p className="text-sm">Add your first todo above.</p>
          </div>
        )}

        {todos && todos.length > 0 && (
          <>
            <ul className="flex flex-col gap-2">
              {todos.map((todo) => (
                <TodoItem
                  key={todo.id}
                  todo={todo}
                  busy={busyId === todo.id}
                  onToggle={handleToggle}
                  onDelete={handleDelete}
                />
              ))}
            </ul>
            <p className="mt-3 text-sm text-zinc-500">
              {left} of {todos.length} left
            </p>
          </>
        )}
      </main>
    </div>
  );
}
