// ============================================================
// next.config.ts — Next.js settings for the web service.
//
// Proxy to the Go API
// -------------------
// The browser only ever talks to web (localhost:3000). Any request
// to /api/... is forwarded by the Next.js server to the API service:
//
//   browser ──▶ localhost:3000/api/v1/todos ──▶ API_URL/api/v1/todos
//
// Why a proxy instead of calling localhost:8080 from the browser?
//   - Same origin: the browser sees one address, so the Go API needs
//     no CORS headers.
//   - The browser never learns where the API lives. Only this server
//     knows API_URL — the same idea as the Gateway on Kubernetes later
//     (/ → web, /api/... → the API services).
//
// API_URL comes from .env.local (see .env.example). It has no
// NEXT_PUBLIC_ prefix on purpose: it is only needed on the server
// and is never sent to the browser.
// ============================================================

import type { NextConfig } from "next";

// Where the Go API runs. Default = running it natively with `make dev`.
const apiUrl = process.env.API_URL ?? "http://localhost:8080";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },

  // /api/anything → <API_URL>/api/anything (path and query kept as-is)
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
