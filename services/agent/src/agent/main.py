"""main.py — builds the FastAPI app.

Like the router setup in services/todo/internal/handlers/routes.go:
config → logging → (on start: database) → middleware → routes.

`lifespan` runs code once when the server starts (before the first
request) and once when it stops: open the database pool, the
HTTP client used to call the todo service and the LLM client, then close
them cleanly on shutdown (Ctrl+C / SIGTERM).

Every request goes through `request_context` (middleware):
  1. take X-Request-ID from the caller, or make a new one
  2. store it so every log line of this request includes it
  3. send it back in the response header
  4. log one "request completed" line with status and duration
Reusing the caller's X-Request-ID is what lets one ID follow a
request from web → agent → api in the logs.

Errors use the same JSON shape as the Go services,
{"error": "...", "request_id": "..."}, instead of FastAPI's default
{"detail": ...} — web/lib/api.ts reads "error" from every service.
"""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus

import httpx
import httpx2
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from agent.config import get_settings
from agent.db import open_pool
from agent.llm import create_llm
from agent.log import get_logger, request_id_var, setup_logging
from agent.migrate import migrate
from agent.routes import actions, chat, conversation, health, usage
from agent.todo_client import TodoClient

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # ── startup ──
    app.state.pool = await open_pool(settings)
    await migrate(app.state.pool)  # create/update tables before serving
    # One shared HTTP client for the whole service: it keeps connections
    # to the todo service open and reuses them (like a database pool, for HTTP).
    app.state.http = httpx2.AsyncClient(timeout=settings.api_timeout_seconds)
    app.state.todos = TodoClient(app.state.http, settings.todo_url)
    # The LLM client (OpenRouter SDK) gets its own httpx client — the SDK
    # is built on httpx; our api calls use httpx2.
    app.state.llm_http = httpx.AsyncClient()
    app.state.llm = create_llm(settings, app.state.llm_http)
    yield  # ← the server handles requests while we're paused here
    # ── shutdown ──
    await app.state.llm_http.aclose()
    await app.state.http.aclose()
    await app.state.pool.close()
    log.info("server stopped cleanly")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format, settings.env)

    app = FastAPI(
        title="agent",
        lifespan=lifespan,
        # Interactive API docs at /docs, only while developing.
        docs_url="/docs" if settings.env == "development" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.env == "development" else None,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            log.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000),
                },
            )
            return response
        finally:
            request_id_var.reset(token)  # this request is done; forget its ID

    # ── Errors in the shared shape ───────────────────────────
    def error_response(status: int, message: str, headers=None) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={"error": message, "request_id": request_id_var.get()},
            headers=headers,  # e.g. Retry-After on a 429
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        # 404 unknown path, 405 wrong method, raise HTTPException(401, ...) …
        message = str(exc.detail)
        if message == HTTPStatus(exc.status_code).phrase:
            message = message.lower()  # FastAPI's own "Not Found" → "not found", like Go
        return error_response(exc.status_code, message, getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Body didn't match the expected model, e.g. a missing field.
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"] if p != "body")
        return error_response(400, f"{field}: {first['msg']}".lower() if field else first["msg"])

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # A bug: log the details, but never send them to the client.
        log.error("unhandled error", exc_info=exc)
        return error_response(500, "internal server error")

    app.include_router(health.router)
    app.include_router(conversation.router)
    app.include_router(chat.router)
    app.include_router(actions.router)
    app.include_router(usage.router)

    log.info("starting agent", extra={"addr": f"{settings.host}:{settings.port}"})
    return app


app = create_app()
