// ============================================================
// proxy.ts — forwards /api/... to the right backend service.
//
//   browser ──▶ web:3000/api/v1/auth/...  ──▶ AUTH_URL/api/v1/auth/...    (Go auth service)
//   browser ──▶ web:3000/api/v1/agent/... ──▶ AGENT_URL/api/v1/agent/...  (Python agent)
//   browser ──▶ web:3000/api/v1/todos/... ──▶ TODO_URL/api/v1/todos/...   (Go todo service)
//
// The browser only ever talks to web (one address). Which service
// answers is decided HERE, by the path. This is the same job a
// gateway / ingress does in Kubernetes (step 4–5: `/api/agent` →
// agent, `/api/todos` → todo, …) — for now web does it itself.
//
// Proxy (Next.js 16's new name for "middleware") runs on the
// server before every request that matches `config.matcher`.
//
// Why here and not as a `rewrites()` rule in next.config.ts?
// next.config.ts is read once during `next build` and baked into
// the build output — so the URLs would be frozen inside the Docker
// image. Proxy runs per request and reads the env vars when the
// container *starts*. One image works everywhere: on your Mac
// (localhost:8082), in Docker, on Kubernetes (http://todo:8082).
//
// Why a proxy at all: the browser sees one address, so the
// services need no CORS headers and the browser never learns where
// they live. The *_URL vars have no NEXT_PUBLIC_ prefix: they stay
// on the server.
// ============================================================

import { NextResponse, type NextRequest } from "next/server";

// Which service owns which path — one row per backend service.
// There is no "everything else" row any more: since step 3c every
// path has exactly one owner (the monolith that took the rest is gone).
const ROUTES = [
  { prefix: "/api/v1/auth", env: "AUTH_URL", fallback: "http://localhost:8081" },
  { prefix: "/api/v1/todos", env: "TODO_URL", fallback: "http://localhost:8082" },
  { prefix: "/api/v1/agent", env: "AGENT_URL", fallback: "http://localhost:8083" },
] as const;

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // "/api/v1/agent" or "/api/v1/agent/…" — but not "/api/v1/agents".
  const route = ROUTES.find((r) => pathname === r.prefix || pathname.startsWith(r.prefix + "/"));

  // No service owns this path: answer 404 here, in the same JSON shape
  // the services use for errors (lib/api.ts shows `error` to the user).
  if (!route) return NextResponse.json({ error: "not found" }, { status: 404 });

  // Read at request time — not baked in at build time.
  const base = process.env[route.env] ?? route.fallback;

  // Same path and query string, different host:
  // /api/v1/agent/chat → http://localhost:8083/api/v1/agent/chat
  return NextResponse.rewrite(new URL(pathname + search, base));
}

// Only run for /api/... — pages and static files are untouched.
export const config = {
  matcher: "/api/:path*",
};
