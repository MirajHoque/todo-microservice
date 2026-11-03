// ============================================================
// proxy.ts — forwards /api/... to the Go API.
//
//   browser ──▶ web:3000/api/v1/todos ──▶ API_URL/api/v1/todos
//
// Proxy (Next.js 16's new name for "middleware") runs on the
// server before every request that matches `config.matcher`.
//
// Why here and not as a `rewrites()` rule in next.config.ts?
// next.config.ts is read once during `next build` and baked into
// the build output — so API_URL would be frozen inside the Docker
// image. Proxy runs per request and reads API_URL when the
// container *starts*. One image works everywhere: on your Mac
// (localhost:8080), in Docker, on Kubernetes (http://api:8080).
//
// Why a proxy at all: the browser sees one address, so the Go API
// needs no CORS headers and the browser never learns where the API
// lives. API_URL has no NEXT_PUBLIC_ prefix: it stays on the server.
// ============================================================

import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  // Read at request time — not baked in at build time.
  const apiUrl = process.env.API_URL ?? "http://localhost:8080";

  // Same path and query string, different host:
  // /api/v1/todos?x=1 → http://localhost:8080/api/v1/todos?x=1
  const target = new URL(request.nextUrl.pathname + request.nextUrl.search, apiUrl);
  return NextResponse.rewrite(target);
}

// Only run for /api/... — pages and static files are untouched.
export const config = {
  matcher: "/api/:path*",
};
