// ============================================================
// app/todos/page.tsx — the /todos page.
//
// TEMPORARY placeholder so login has somewhere to land: it shows
// who is logged in and a logout button. The real todo list comes
// in step 1c.5.
// ============================================================

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";

import { logout } from "@/lib/api";
import { clearSession, getEmail, getToken } from "@/lib/session";

// Read the email from localStorage. useSyncExternalStore is React's
// way to read a value that lives outside React: getEmail in the
// browser, and null while rendering on the server (no localStorage).
const noSubscribe = () => () => {};

export default function TodosPage() {
  const router = useRouter();
  const email = useSyncExternalStore(noSubscribe, getEmail, () => null);

  // Not logged in? This page needs a token, so go to /login.
  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  async function handleLogout() {
    // Tell the API (it clears the agent's memory for this user),
    // then forget the token in the browser. Even if the API call
    // fails, the user is logged out locally.
    if (getToken()) await logout().catch(() => {});
    clearSession();
    router.push("/login");
  }

  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-8 text-center shadow-sm ring-1 ring-zinc-200">
        <h1 className="mb-2 text-2xl font-semibold">Logged in</h1>
        <p className="mb-6 text-zinc-600">{email ?? "…"}</p>
        <p className="mb-6 text-sm text-zinc-500">Your todos will appear here in step 1c.5.</p>
        <button
          onClick={handleLogout}
          className="rounded-md bg-zinc-800 px-4 py-2 font-medium text-white hover:bg-zinc-900"
        >
          Log out
        </button>
      </div>
    </main>
  );
}
