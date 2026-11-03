// ============================================================
// components/auth-form.tsx — the form shared by /login and /register.
//
// Both pages need the same thing: email + password, call the API,
// save the token, go to /todos. Only the API call and the wording
// differ, so one component takes a `mode` instead of two copies.
//
// 'use client' — this component runs in the browser: it has state
// (what you typed), reacts to clicks and uses localStorage. Pages
// without these needs stay server components (the default).
// ============================================================

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { ApiError, login, register } from "@/lib/api";
import { getToken, saveSession } from "@/lib/session";

type Mode = "login" | "register";

// Everything that differs between the two pages.
const TEXT = {
  login: {
    title: "Welcome back",
    button: "Log in",
    busy: "Logging in…",
    switchText: "Don't have an account?",
    switchLink: { href: "/register", label: "Register" },
  },
  register: {
    title: "Create an account",
    button: "Register",
    busy: "Creating account…",
    switchText: "Already have an account?",
    switchLink: { href: "/login", label: "Log in" },
  },
} as const;

// true once React runs in the browser, false in the server-rendered HTML.
// The page's HTML arrives before its JavaScript; a click in that gap
// would make the browser submit the form itself (a full page reload)
// instead of running handleSubmit. So the button starts disabled.
const noSubscribe = () => () => {};
const useHydrated = () => useSyncExternalStore(noSubscribe, () => true, () => false);

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const text = TEXT[mode];

  // React state: when one of these changes, the form re-renders.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hydrated = useHydrated();

  // Already logged in? Skip the form. useEffect runs only in the
  // browser, after the page appears — localStorage exists there.
  useEffect(() => {
    if (getToken()) router.replace("/todos");
  }, [router]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); // stop the browser's own full-page form submit
    setError(null);

    // Same rule as the API (RegisterRequest.Validate), checked early
    // so the user gets instant feedback. The API still checks too —
    // never trust the browser alone.
    if (mode === "register" && password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setBusy(true);
    try {
      const res = mode === "login" ? await login(email, password) : await register(email, password);
      saveSession(res.token, res.user.email);
      router.push("/todos");
    } catch (err) {
      // ApiError carries the API's own message ("invalid email or
      // password", "email already registered", ...). Anything else
      // means we never got an answer — e.g. web or the network is down.
      setError(err instanceof ApiError ? err.message : "Network error, please try again");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-xl bg-white p-8 shadow-sm ring-1 ring-zinc-200"
      >
        <h1 className="mb-6 text-2xl font-semibold">{text.title}</h1>

        {error && (
          <p role="alert" className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        <label className="mb-4 block">
          <span className="mb-1 block text-sm font-medium text-zinc-700">Email</span>
          <input
            type="email"
            required
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-600 focus:outline-none"
          />
        </label>

        <label className="mb-6 block">
          <span className="mb-1 block text-sm font-medium text-zinc-700">Password</span>
          <input
            type="password"
            required
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            placeholder={mode === "login" ? "Your password" : "At least 8 characters"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-600 focus:outline-none"
          />
        </label>

        <button
          type="submit"
          disabled={busy || !hydrated}
          className="w-full rounded-md bg-blue-600 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-60"
        >
          {busy ? text.busy : text.button}
        </button>

        <p className="mt-4 text-center text-sm text-zinc-600">
          {text.switchText}{" "}
          <Link href={text.switchLink.href} className="text-blue-600 hover:underline">
            {text.switchLink.label}
          </Link>
        </p>
      </form>
    </main>
  );
}
