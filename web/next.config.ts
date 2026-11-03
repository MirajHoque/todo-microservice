// ============================================================
// next.config.ts — Next.js settings for the web service.
//
// This file is read once during `next build` and baked into the
// build output, so it must not depend on per-environment values
// like API_URL. The /api → Go API forwarding lives in proxy.ts,
// which reads API_URL at runtime.
// ============================================================

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // `next build` also writes .next/standalone: a minimal server.js
  // plus only the node_modules files it needs. The Docker image
  // copies just that folder, so it stays small (see Dockerfile).
  output: "standalone",

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
};

export default nextConfig;
