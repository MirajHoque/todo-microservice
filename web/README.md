# web — Next.js frontend

The UI service of the todo system (see `docs/ROADMAP.md`).
It owns **no data**: everything it shows comes from the Go API over HTTP.

- Framework: Next.js (App Router) + TypeScript + Tailwind CSS
- Port: **3000**
- Talks to: the api service on `localhost:8080` (wired up in step 1c.2)

## Run it

Like every service, `web` runs natively in its own terminal
(see `docs/LOCAL_DEV.md`):

```bash
cd web
npm install      # first time only — downloads dependencies into node_modules/
npm run dev      # http://localhost:3000, reloads when you save a file
```

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
| `next.config.ts` | Next.js settings |
| `package.json` | This service's dependencies and scripts (like `go.mod` for Go) |
| `package-lock.json` | Exact dependency versions (like `go.sum`) |
| `AGENTS.md` | Note from Next.js for AI coding tools; `next dev` recreates it |
