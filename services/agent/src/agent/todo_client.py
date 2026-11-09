"""todo_client.py — the agent's way to read and change todos.

The `todos` table belongs to the api service (ROADMAP rule 3). The
agent can't even connect to that database, so every todo action is
an HTTP call to the api — the same endpoints web uses:

    list    GET    {API_URL}/api/v1/todos
    create  POST   {API_URL}/api/v1/todos
    update  PATCH  {API_URL}/api/v1/todos/{id}
    delete  DELETE {API_URL}/api/v1/todos/{id}

Every call carries two headers from the incoming request:
  Authorization: Bearer <the user's own JWT>
      The agent acts *as the user*, with no extra power. The api checks
      ownership exactly as it does for web, so even a confused or
      tricked LLM can only ever touch this user's todos.
  X-Request-ID: <the same id>
      One chat message can be followed through both services' logs.

Python version of web/lib/api.ts. The agent's tools (step 2e) call these.
"""

import time
from typing import Annotated, Any
from urllib.parse import quote

import httpx2
from fastapi import Depends, Request

from agent.auth import Caller
from agent.log import get_logger, request_id_var

log = get_logger(__name__)


class TodoAPIError(Exception):
    """The api said no (4xx/5xx) or couldn't be reached.

    `message` is the api's own "error" text ("todo not found", …) —
    useful to hand back to the LLM so it can explain what went wrong.
    """

    def __init__(self, status: int, message: str, request_id: str | None = None) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message
        self.request_id = request_id


class TodoClient:
    def __init__(self, http: httpx2.AsyncClient, base_url: str) -> None:
        self._http = http  # shared, reuses connections (created in main.py)
        self._base = base_url.rstrip("/") + "/api/v1"

    # ── one method per endpoint ──────────────────────────────

    async def list_todos(self, caller: Caller) -> list[dict[str, Any]]:
        return await self._request("GET", "/todos", caller) or []

    async def create_todo(
        self,
        caller: Caller,
        title: str,
        priority: str = "medium",
        description: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title, "priority": priority}
        if description:
            body["description"] = description
        return await self._request("POST", "/todos", caller, json=body)

    async def update_todo(self, caller: Caller, todo_id: str, **changes: Any) -> dict[str, Any]:
        """Change only the given fields, e.g. update_todo(c, id, done=True)."""
        path = f"/todos/{quote(todo_id, safe='')}"  # quote: an id can't change the path
        return await self._request("PATCH", path, caller, json=changes)

    async def delete_todo(self, caller: Caller, todo_id: str) -> None:
        await self._request("DELETE", f"/todos/{quote(todo_id, safe='')}", caller)

    # ── the one place that actually sends HTTP ───────────────

    async def _request(
        self, method: str, path: str, caller: Caller, json: dict[str, Any] | None = None
    ) -> Any:
        headers = {"Authorization": f"Bearer {caller.token}"}
        if request_id := request_id_var.get():
            headers["X-Request-ID"] = request_id

        start = time.perf_counter()
        try:
            res = await self._http.request(method, self._base + path, headers=headers, json=json)
        except httpx2.TimeoutException:
            self._log(method, path, None, start, error="timeout")
            raise TodoAPIError(504, "the todo api did not answer in time") from None
        except httpx2.HTTPError as exc:  # connection refused, DNS, …
            self._log(method, path, None, start, error=type(exc).__name__)
            raise TodoAPIError(503, "cannot reach the todo api") from None

        self._log(method, path, res.status_code, start)
        if res.status_code >= 400:
            try:
                body = res.json()
            except ValueError:
                body = {}
            raise TodoAPIError(res.status_code, body.get("error", res.reason_phrase))
        if res.status_code == 204:  # DELETE: no body
            return None
        return res.json()

    def _log(
        self, method: str, path: str, status: int | None, start: float, error: str | None = None
    ) -> None:
        extra: dict[str, Any] = {
            "action": "api_call",
            "method": method,
            "path": "/api/v1" + path,
            "duration_ms": round((time.perf_counter() - start) * 1000),
        }
        if status is not None:
            extra["status"] = status
        if error:
            extra["error"] = error
            log.warning("todo api call failed", extra=extra)
        else:
            log.info("todo api call", extra=extra)


def get_todo_client(request: Request) -> TodoClient:
    return request.app.state.todos


# Use in a route:  async def handler(todos: Todos): ...
Todos = Annotated[TodoClient, Depends(get_todo_client)]
