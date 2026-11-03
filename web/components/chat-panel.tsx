// ============================================================
// components/chat-panel.tsx — the "AI Assistant" box on /todos.
//
// You type a message → chat() sends POST /api/v1/agent/chat → the
// Go api's orchestrator agent answers, and may add / complete /
// delete todos with its tools. So after every reply we call
// onAgentReplied() and the page reloads the list.
//
// The conversation shown here lives only in this component (gone
// on reload). The agent's own memory lives in the Go api, per user,
// and is cleared on logout.
// ============================================================

"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, chat } from "@/lib/api";

type Message = {
  role: "user" | "agent";
  text: string;
  error?: boolean; // shown in red
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

  async function handleSend(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const text = input.trim();
    if (!text || thinking) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setThinking(true);
    try {
      const reply = await chat(text); // a real LLM call: takes a few seconds
      setMessages((m) => [...m, { role: "agent", text: reply }]);
      onAgentReplied();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      const msg = err instanceof ApiError ? err.message : "Network error, please try again";
      setMessages((m) => [...m, { role: "agent", text: msg, error: true }]);
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
          <p
            key={i}
            className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
              m.role === "user"
                ? "self-end bg-blue-600 text-white"
                : m.error
                  ? "self-start bg-red-50 text-red-700"
                  : "self-start bg-zinc-100 text-zinc-800"
            }`}
          >
            {m.text}
          </p>
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
