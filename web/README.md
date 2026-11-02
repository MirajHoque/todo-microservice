# web — Next.js frontend

The UI service of the todo system (see `docs/ROADMAP.md`).
It owns **no data**: everything it shows comes from the Go API over HTTP.

- Framework: Next.js (App Router) + TypeScript + Tailwind CSS
- Port: **3000**
- Talks to: the api service at `API_URL` (default `http://localhost:8080`)

## How it reaches the API

The browser only talks to web. Requests to `/api/...` are forwarded by
the Next.js server to the Go API (a *rewrite*, set up in `next.config.ts`):

```
browser ──▶ localhost:3000/api/v1/todos ──▶ localhost:8080/api/v1/todos (Go api)
```

So the Go API needs no CORS headers, and the browser never learns
where the API lives. If the API is down, web's pages still load, but
`/api/...` calls return 500.

## Run it

Like every service, `web` runs natively in its own terminal
(see `docs/LOCAL_DEV.md`). Start Postgres and the api first.

```bash
cd web
cp .env.example .env.local   # first time only — sets API_URL
npm install                  # first time only — downloads dependencies into node_modules/
npm run dev                  # http://localhost:3000, reloads when you save a file
```

Check the proxy: `curl localhost:3000/api/v1/todos` should return
`{"error":"missing authorization header"}` — that answer comes from the Go API.

## Other commands

| Command | What it does |
|---|---|
| `npm run lint` | Check the code with ESLint |
| `npm run build` | Production build (also type-checks) |
| `npm start` | Serve the production build |

## Layout

| Path | What it is |
|---|---|
| `app/` | Pages. Folders become URLs: `app/page.tsx` is `/`, `app/todos/page.tsx` will be `/todos` |
| `app/layout.tsx` | Wraps every page (`<html>`, `<body>`, fonts) |
| `public/` | Static files served as-is (images, icons) |
| `next.config.ts` | Next.js settings, including the `/api` proxy |
| `.env.example` | Template for `.env.local` (your local settings, git-ignored) |
| `package.json` | This service's dependencies and scripts (like `go.mod` for Go) |
| `package-lock.json` | Exact dependency versions (like `go.sum`) |
| `AGENTS.md` | Note from Next.js for AI coding tools; `next dev` recreates it |
