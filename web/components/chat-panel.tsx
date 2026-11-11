// ============================================================
// components/chat-panel.tsx — the "AI Assistant" box on /todos.
//
// You type a message → chat() sends POST /api/v1/agent/chat →
// proxy.ts forwards it to the Python agent service (AGENT_URL),
// which may add / complete / delete todos with its tools (through
// the Go api). So after every reply we call onAgentReplied() and
// the page reloads the list.
//
// The conversation shown here lives only in this component (gone
// on reload). The agent's own memory lives in its database
// (agent_db), per user, and is cleared on logout.
//
// Guardrail (step 2i.1): the agent can't delete todos. When it wants
// to, its reply carries a pending_action and we show Confirm / Cancel
// buttons. Only YOUR click deletes — the agent has no way to press it.
// ============================================================

"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, cancelAction, chat, confirmAction } from "@/lib/api";
import type { PendingAction } from "@/lib/types";

type Message = {
  role: "user" | "agent";
  text: string;
  error?: boolean; // shown in red
  action?: PendingAction; // show Confirm / Cancel under this message
  actionDone?: boolean; // clicked: hide the buttons
};

type Props = {
  onAgentReplied: () => void; // the agent may have changed todos
  onUnauthorized: () => void; // token missing or expired (401)
};

const GREETING: Message = {
  role: "agent",
  text: 'Hi! I can manage your todos. Try "add a todo to buy milk, high priority" or "what\'s left to do?"',
};

export function ChatPanel({ onAgentReplied, onUnauthorized }: Props) {
  const [messages, setMessages] = useState<Message[]>([GREETING]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);

  // Keep the newest message in view. A ref points at the real DOM
  // element so we can scroll it — React state can't do that.
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, thinking]);

  // Shows an error from any call as a red agent message (401 → login).
  function showError(err: unknown) {
    if (err instanceof ApiError && err.status === 401) {
      onUnauthorized();
      return;
    }
    const msg = err instanceof ApiError ? err.message : "Network error, please try again";
    setMessages((m) => [...m, { role: "agent", text: msg, error: true }]);
  }

  async function handleSend(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const text = input.trim();
    if (!text || thinking) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setThinking(true);
    try {
      const res = await chat(text); // a real LLM call: takes a few seconds
      setMessages((m) => [
        // A new proposal replaces the older one on the server (one per
        // user), so hide older buttons. Without one, they stay usable.
        ...(res.pending_action ? m.map((x) => ({ ...x, actionDone: true })) : m),
        { role: "agent", text: res.reply, action: res.pending_action },
      ]);
      onAgentReplied();
    } catch (err) {
      showError(err);
    } finally {
      setThinking(false);
    }
  }

  // Confirm or Cancel a proposed deletion — the only way todos get deleted.
  async function handleAction(index: number, action: PendingAction, confirm: boolean) {
    // Hide the buttons right away, so a double click can't send twice.
    setMessages((m) => m.map((x, i) => (i === index ? { ...x, actionDone: true } : x)));
    setThinking(true);
    try {
      const res = confirm ? await confirmAction(action.id) : await cancelAction(action.id);
      setMessages((m) => [...m, { role: "agent", text: res.reply }]);
      if (confirm) onAgentReplied(); // todos were deleted: reload the list
    } catch (err) {
      showError(err);
    } finally {
      setThinking(false);
    }
  }

  return (
    <section className="mt-8 rounded-xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
      <h2 className="mb-3 flex items-center gap-2 font-semibold">
        <span aria-hidden>🤖</span> AI Assistant
        <span className="text-sm font-normal text-zinc-500">Ask me to manage your todos</span>
      </h2>

      <div ref={listRef} className="mb-3 flex max-h-80 flex-col gap-2 overflow-y-auto" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`flex max-w-[85%] flex-col gap-2 ${m.role === "user" ? "self-end" : "self-start"}`}>
            <p
              className={`whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-blue-600 text-white"
                  : m.error
                    ? "bg-red-50 text-red-700"
                    : "bg-zinc-100 text-zinc-800"
              }`}
            >
              {m.text}
            </p>
            {m.action && !m.actionDone && (
              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm">
                <span className="text-red-800">
                  Delete {m.action.todos.map((t) => `"${t.title}"`).join(", ")}?
                </span>
                <button
                  type="button"
                  onClick={() => handleAction(i, m.action!, true)}
                  disabled={thinking}
                  className="rounded-md bg-red-600 px-3 py-1 font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  Confirm
                </button>
                <button
                  type="button"
                  onClick={() => handleAction(i, m.action!, false)}
                  disabled={thinking}
                  className="rounded-md border border-zinc-300 bg-white px-3 py-1 font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-60"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        ))}
        {thinking && (
          <p className="self-start animate-pulse rounded-2xl bg-zinc-100 px-3 py-2 text-sm text-zinc-500">
            Thinking…
          </p>
        )}
      </div>

      <form onSubmit={handleSend} className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask the assistant…"
          aria-label="Message to the assistant"
          className="min-w-0 flex-1 rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-600 focus:outline-none"
        />
        <button
          type="submit"
          disabled={thinking || !input.trim()}
          className="rounded-md bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-60"
        >
          Send
        </button>
      </form>
    </section>
  );
}
