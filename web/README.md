# web — Next.js frontend

The UI service of the todo system (see `docs/ROADMAP.md`).
It owns **no data**: everything it shows comes from the Go API over HTTP.

- Framework: Next.js (App Router) + TypeScript + Tailwind CSS
- Port: **3000**
- Talks to: the api service at `API_URL` (default `http://localhost:8080`)

## Pages

| URL | What it does |
|---|---|
| `/` | Sends you to `/todos` (logged in) or `/login` |
| `/login`, `/register` | Email + password; saves the JWT in localStorage |
| `/todos` | Your todos (add, tick, delete) + the AI Assistant chat |

## How it reaches the API

The browser only talks to web. Requests to `/api/...` are forwarded by
the Next.js server to the Go API (see `proxy.ts`):

```
browser ──▶ localhost:3000/api/v1/todos ──▶ API_URL/api/v1/todos (Go api)
```

So the Go API needs no CORS headers, and the browser never learns
where the API lives. If the API is down, web's pages still load, but
`/api/...` calls fail with "Cannot reach the api".

`API_URL` is read when the server **starts** (not when it is built),
so one Docker image works on your Mac, in Docker and on Kubernetes.

## Run it (day to day)

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

## Run it in Docker

The `Dockerfile` builds a small production image (Next.js
`standalone` output, non-root user, healthcheck). Kubernetes will
use this image in step 4.

```bash
docker build -t todo-web web/                 # from the repo root
docker run --rm -p 3000:3000 \
  -e API_URL=http://host.docker.internal:8080 todo-web
```

`host.docker.internal` means "your Mac" from inside a container —
`localhost` there would be the container itself. Keep the api
running natively (`make dev` in `services/api`).

## Other commands

| Command | What it does |
|---|---|
| `npm run lint` | Check the code with ESLint |
| `npm run build` | Production build (also type-checks) |
| `npm start` | Serve the production build |

## Layout

| Path | What it is |
|---|---|
| `app/` | Pages. Folders become URLs: `app/login/page.tsx` is `/login` |
| `app/layout.tsx` | Wraps every page (`<html>`, `<body>`, fonts) |
| `components/` | Pieces used by pages: auth form, todo row, chat panel |
| `lib/types.ts` | The API contract as TypeScript types (mirrors the Go models) |
| `lib/api.ts` | One function per API endpoint (`login()`, `listTodos()`, …) |
| `lib/session.ts` | Saves/reads the JWT in localStorage |
| `proxy.ts` | Forwards `/api/...` to `API_URL` |
| `next.config.ts` | Next.js build settings (`output: "standalone"`) |
| `public/` | Static files served as-is (images, icons) |
| `Dockerfile`, `.dockerignore` | Builds the production image |
| `.env.example` | Template for `.env.local` (your local settings, git-ignored) |
| `package.json` | This service's dependencies and scripts (like `go.mod` for Go) |
| `package-lock.json` | Exact dependency versions (like `go.sum`) |
| `AGENTS.md` | Note from Next.js for AI coding tools; `next dev` recreates it |
