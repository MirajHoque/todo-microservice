// ============================================================
// components/todo-item.tsx — one row in the todo list.
//
// It only *shows* a todo and reports clicks to its parent
// (onToggle / onDelete). It never calls the API itself — the
// page owns the list and talks to the API. Keeping "show" and
// "do" apart makes each piece small and easy to follow.
// ============================================================

import type { Priority, Todo } from "@/lib/types";

// Tailwind classes for each priority badge.
const BADGE: Record<Priority, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-green-50 text-green-700",
};

type Props = {
  todo: Todo;
  busy: boolean; // a request for this row is in flight
  onToggle: (todo: Todo) => void;
  onDelete: (todo: Todo) => void;
};

export function TodoItem({ todo, busy, onToggle, onDelete }: Props) {
  return (
    <li className="flex items-center gap-3 rounded-lg bg-white px-4 py-3 shadow-sm ring-1 ring-zinc-200">
      <input
        type="checkbox"
        checked={todo.done}
        disabled={busy}
        onChange={() => onToggle(todo)}
        aria-label={todo.done ? `Mark "${todo.title}" as not done` : `Mark "${todo.title}" as done`}
        className="size-5 accent-blue-600"
      />

      {/* React escapes text automatically — no escapeHtml() needed
          like in the old Go template. */}
      <span className={`flex-1 break-words ${todo.done ? "text-zinc-400 line-through" : ""}`}>
        {todo.title}
      </span>

      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[todo.priority]}`}>
        {todo.priority}
      </span>

      <button
        onClick={() => onDelete(todo)}
        disabled={busy}
        aria-label={`Delete "${todo.title}"`}
        className="rounded px-2 text-zinc-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
      >
        ✕
      </button>
    </li>
  );
}
