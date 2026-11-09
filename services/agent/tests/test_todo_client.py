"""TodoClient tests.

Part 1 uses a FAKE api (httpx2.MockTransport): a Python function that
plays the api, so we can check exactly what the client sends and how
it handles every answer — no network, nothing running.

Part 2 talks to the REAL Go api (skipped if it isn't running):
the agent service and the api service, actually talking.
"""

import asyncio
import json
import uuid

import httpx2
import pytest

from agent.auth import Caller
from agent.log import request_id_var
from agent.todo_client import TodoAPIError, TodoClient

CALLER = Caller(user_id="u-1", token="the-users-jwt")


def run(coro):
    """Run one async call from a normal (sync) test."""
    return asyncio.run(coro)


def fake_api(handler) -> TodoClient:
    """A TodoClient whose 'api' is the given function."""
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return TodoClient(http, "http://api.test")


# ── Part 1: against a fake api ───────────────────────────────


def test_forwards_the_users_token_and_request_id():
    seen = {}

    def api(req: httpx2.Request) -> httpx2.Response:
        seen.update(method=req.method, url=str(req.url), headers=req.headers)
        return httpx2.Response(200, json=[])

    async def call():
        token = request_id_var.set("req-42")  # as if inside a request
        try:
            return await fake_api(api).list_todos(CALLER)
        finally:
            request_id_var.reset(token)

    assert run(call()) == []
    assert seen["method"] == "GET"
    assert seen["url"] == "http://api.test/api/v1/todos"
    assert seen["headers"]["authorization"] == "Bearer the-users-jwt"
    assert seen["headers"]["x-request-id"] == "req-42"


def test_create_sends_json_body():
    def api(req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        assert (req.method, req.url.path) == ("POST", "/api/v1/todos")
        assert body == {"title": "Buy milk", "priority": "high"}
        return httpx2.Response(201, json={"id": "t1", **body, "done": False})

    todo = run(fake_api(api).create_todo(CALLER, "Buy milk", priority="high"))
    assert todo["id"] == "t1"


def test_update_sends_only_changed_fields_and_escapes_id():
    def api(req: httpx2.Request) -> httpx2.Response:
        assert req.method == "PATCH"
        assert req.url.raw_path == b"/api/v1/todos/a%2Fb"  # "/" in an id can't change the path
        assert json.loads(req.content) == {"done": True}
        return httpx2.Response(200, json={"id": "a/b", "done": True})

    assert run(fake_api(api).update_todo(CALLER, "a/b", done=True))["done"] is True


def test_delete_returns_none_on_204():
    def api(req: httpx2.Request) -> httpx2.Response:
        assert req.method == "DELETE"
        return httpx2.Response(204)

    assert run(fake_api(api).delete_todo(CALLER, "t1")) is None


def test_list_null_becomes_empty_list():
    # Go encodes an empty (nil) slice as `null`, not `[]`.
    api = fake_api(lambda r: httpx2.Response(200, content=b"null"))
    assert run(api.list_todos(CALLER)) == []


def test_api_error_message_is_kept():
    def api(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"error": "todo not found", "request_id": "x"})

    with pytest.raises(TodoAPIError) as err:
        run(fake_api(api).update_todo(CALLER, "nope", done=True))
    assert (err.value.status, err.value.message) == (404, "todo not found")


def test_api_down_is_503():
    def api(req: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(TodoAPIError) as err:
        run(fake_api(api).list_todos(CALLER))
    assert err.value.status == 503


def test_api_too_slow_is_504():
    def api(req: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("too slow")

    with pytest.raises(TodoAPIError) as err:
        run(fake_api(api).list_todos(CALLER))
    assert err.value.status == 504


# ── Part 2: against the real Go api ──────────────────────────

API_URL = "http://localhost:8080"


@pytest.fixture
def real_caller() -> Caller:
    """Register a fresh user on the real api; skip if the api isn't running."""
    try:
        body = _register()
    except httpx2.HTTPError:
        pytest.skip("Go api not running — start it with `make dev` in services/api")
    return Caller(user_id=body["user"]["id"], token=body["token"])


def test_full_round_trip_with_the_real_api(real_caller):
    async def scenario():
        async with httpx2.AsyncClient(timeout=10) as http:
            todos = TodoClient(http, API_URL)
            created = await todos.create_todo(real_caller, "Written by the agent", priority="high")
            assert created["user_id"] == real_caller.user_id  # the api says: it's the user's

            listed = await todos.list_todos(real_caller)
            assert [t["id"] for t in listed] == [created["id"]]

            done = await todos.update_todo(real_caller, created["id"], done=True)
            assert done["done"] is True and done["done_at"]

            await todos.delete_todo(real_caller, created["id"])
            assert await todos.list_todos(real_caller) == []

            with pytest.raises(TodoAPIError) as err:
                await todos.delete_todo(real_caller, created["id"])
            assert (err.value.status, err.value.message) == (404, "todo not found")

    run(scenario())


def test_cannot_touch_another_users_todos(real_caller):
    # A second user's token can't see or change the first user's todo:
    # the api enforces it — the agent needs no extra code for this.
    other_user = _register()
    other = Caller(user_id=other_user["user"]["id"], token=other_user["token"])

    async def scenario():
        async with httpx2.AsyncClient(timeout=10) as http:
            todos = TodoClient(http, API_URL)
            mine = await todos.create_todo(real_caller, "private")
            assert await todos.list_todos(other) == []
            with pytest.raises(TodoAPIError) as err:
                await todos.delete_todo(other, mine["id"])
            assert err.value.status == 404  # "not found" — not even "forbidden": no leak
            assert len(await todos.list_todos(real_caller)) == 1

    run(scenario())


def _register() -> dict:
    """Create a fresh user on the real api → {"token": ..., "user": {...}}."""
    email = f"agent-test-{uuid.uuid4().hex[:8]}@example.com"
    res = httpx2.post(
        f"{API_URL}/api/v1/auth/register",
        json={"email": email, "password": "password123"},
        timeout=5,
    )
    return res.json()
