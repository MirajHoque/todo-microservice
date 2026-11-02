// ============================================================
// app/page.tsx — the home page (/).
//
// There is nothing to show here: logged-in users go to /todos,
// everyone else to /login. The token lives in localStorage, which
// only the browser can read, so this is a client component that
// decides after it loads.
// ============================================================

"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { getToken } from "@/lib/session";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getToken() ? "/todos" : "/login");
  }, [router]);

  return null; // shown for a split second before the redirect
}
