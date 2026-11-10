"""Chat tests: the agent loop, with a FAKE model and a FAKE todo api.

The real OpenRouter SDK and the real TodoClient are used — only the
network is replaced (MockTransport):

  FakeModel   answers from a script in OpenRouter's chat format
              ("call create_todo", then "Done!") and records every
              request the agent sent
  FakeTodoAPI keeps todos in a dict, like the Go api would

So every path of the loop is tested for free, the same way every time.
Real OpenRouter calls are made by hand, not in these tests.
"""

import json
from typing import Any

import httpx
import httpx2
import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient
from helpers import auth, make_token
from openrouter import OpenRouter

from agent.config import get_settings
from agent.llm import create_llm
from agent.main import app
from agent.todo_client import TodoClient

CHAT = "/api/v1/agent/chat"
CONVERSATION = "/api/v1/agent/conversation"


# ── Fakes ────────────────────────────────────────────────────


def call(id_: str, name: str, **args: Any) -> dict:
    """One tool call, as a model returns it (arguments are a JSON string)."""
    fn = {"name": name, "arguments": json.dumps(args)}
    return {"id": id_, "type": "function", "function": fn}


def answer(content: str | None = None, *, tool_calls: list | None = None, **extra) -> dict:
    """One assistant message (finish_reason derived unless given)."""
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    finish = extra.pop("finish_reason", "tool_calls" if tool_calls else "stop")
    msg.update(extra)
    return {"message": msg, "finish_reason": finish}


class FakeModel:
    """Plays OpenRouter's /chat/completions. Each script entry is one answer
    (from `answer(...)`) — or an int to fail with that HTTP status."""

    def __init__(
        self, script: list, model: str = "anthropic/claude-sonnet-5.5", always_fail: int = 0
    ) -> None:
        self.script = list(script)
        self.model = model
        self.always_fail = always_fail  # e.g. 500: every request fails (provider down)
        self.requests: list[dict] = []  # every request body the agent sent

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(req.content))
        if self.always_fail:
            return httpx.Response(self.always_fail, json={"error": {"message": "provider down"}})
        step = self.script.pop(0) if self.script else answer(tool_calls=[call("x", "list_todos")])
        if isinstance(step, int):
            return httpx.Response(step, json={"error": {"code": step, "message": "provider down"}})
        return httpx.Response(
            200,
            json={
                "id": f"gen-{len(self.requests)}",
                "object": "chat.completion",
                "created": 1,
                "model": self.model,
                "system_fingerprint": None,
                "choices": [{"index": 0, **step}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "cost": 0.0001,
                },
            },
        )

    def client(self) -> OpenRouter:
        # The app's real factory (incl. its retry policy), with a 1 s retry budget.
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        settings = get_settings().model_copy(update={"llm_retry_seconds": 1.0})
        return create_llm(settings, http)


class FakeTodoAPI:
    """Plays the Go api's /api/v1/todos endpoints, in memory."""

    def __init__(self) -> None:
        self.todos: dict[str, dict] = {}
        self.seen_auth: list[str] = []

    def handler(self, req: httpx2.Request) -> httpx2.Response:
        self.seen_auth.append(req.headers.get("authorization", ""))
        todo_id = req.url.path.removeprefix("/api/v1/todos").strip("/")
        if req.method == "GET":
            return httpx2.Response(200, json=list(self.todos.values()))
        if req.method == "POST":
            body = json.loads(req.content)
            todo = {"id": f"t{len(self.todos) + 1}", "done": False, **body}
            self.todos[todo["id"]] = todo
            return httpx2.Response(201, json=todo)
        if todo_id not in self.todos:
            return httpx2.Response(404, json={"error": "todo not found"})
        if req.method == "PATCH":
            self.todos[todo_id].update(json.loads(req.content))
            return httpx2.Response(200, json=self.todos[todo_id])
        del self.todos[todo_id]
        return httpx2.Response(204)

    def client(self) -> TodoClient:
        http = httpx2.AsyncClient(transport=httpx2.MockTransport(self.handler))
        return TodoClient(http, "http://api.test")


@pytest.fixture
def chat(db_client):
    """setup(script) → (send, history, model, api), with the fakes swapped into the app."""

    def setup(script: list, **model_kwargs):
        model, api = FakeModel(script, **model_kwargs), FakeTodoAPI()
        app.state.llm = model.client()
        app.state.todos = api.client()
        headers = auth(make_token())

        def send(message: str):
            return db_client.post(CHAT, json={"message": message}, headers=headers)

        def history() -> list[dict]:
            res = db_client.get(CONVERSATION, headers=headers)
            return [m["message"] for m in res.json()["messages"]]

        return send, history, model, api

    return setup


# ── Tests ────────────────────────────────────────────────────


def test_simple_reply_is_saved(chat):
    send, history, model, _ = chat([answer("Hi! How can I help?")])

    res = send("hello")
    assert res.status_code == 200
    assert res.json() == {"reply": "Hi! How can I help?"}

    assert [m["role"] for m in history()] == ["user", "assistant"]
    sent = model.requests[0]
    assert sent["tools"][0]["type"] == "function"  # the tool definitions were sent
    assert sent["messages"][0]["role"] == "system"  # system prompt first …
    assert sent["messages"][1:] == [{"role": "user", "content": "hello"}]  # … then the chat


def test_tool_call_runs_and_everything_is_stored(chat):
    send, history, model, api = chat(
        [
            answer(
                "Adding it.",
                tool_calls=[call("c1", "create_todo", title="Buy milk", priority="high")],
            ),
            answer("Added Buy milk (high)."),
        ]
    )

    assert send("add buy milk, it's urgent").json() == {"reply": "Added Buy milk (high)."}

    # The todo was really created — through the api, as the user.
    assert [t["title"] for t in api.todos.values()] == ["Buy milk"]
    assert api.seen_auth[0].startswith("Bearer ey")  # the user's own JWT

    # The 2nd LLM call carried the tool result, matched by id.
    last = model.requests[1]["messages"][-1]
    assert (last["role"], last["tool_call_id"]) == ("tool", "c1")
    assert "Buy milk" in last["content"]

    # All 4 messages are stored — tool_calls AND the tool result (the 1c.6 fix).
    stored = history()
    assert [m["role"] for m in stored] == ["user", "assistant", "tool", "assistant"]
    assert stored[1]["tool_calls"][0]["function"]["name"] == "create_todo"


def test_next_message_replays_tool_calls_and_reasoning(chat):
    # The model must SEE its earlier tool calls (or it thinks it never did
    # them — the 1c.6 bug), and get its reasoning_details back unchanged.
    reasoning = [{"type": "reasoning.encrypted", "data": "secret-thoughts", "index": 0}]
    send, _, model, _ = chat(
        [
            answer(
                None,
                tool_calls=[call("c1", "create_todo", title="Buy milk", priority="medium")],
                reasoning_details=reasoning,
            ),
            answer("Added."),
            answer("Yes, I added Buy milk."),
        ]
    )
    send("add buy milk")
    send("did you add it?")

    replayed = model.requests[2]["messages"][1:]  # skip the system prompt
    assert [m["role"] for m in replayed] == ["user", "assistant", "tool", "assistant", "user"]
    assert replayed[1]["tool_calls"][0]["id"] == "c1"
    assert replayed[1]["reasoning_details"] == reasoning  # exactly as received


def test_parallel_tool_calls_each_get_a_result(chat):
    send, history, model, api = chat(
        [
            answer(
                tool_calls=[
                    call("a", "create_todo", title="Milk", priority="low"),
                    call("b", "create_todo", title="Bread", priority="low"),
                ]
            ),
            answer("Added both."),
        ]
    )
    send("add milk and bread")

    assert sorted(t["title"] for t in api.todos.values()) == ["Bread", "Milk"]
    results = model.requests[1]["messages"][-2:]
    assert [(m["role"], m["tool_call_id"]) for m in results] == [("tool", "a"), ("tool", "b")]
    assert len(history()) == 5  # user, assistant, tool, tool, assistant


def test_works_with_other_models_and_stop_with_tool_calls(chat):
    # A non-Claude model whose provider reports finish_reason "stop" even
    # though the message has tool calls — the loop must still run them.
    send, _, model, api = chat(
        [
            answer(
                tool_calls=[call("c1", "create_todo", title="Milk", priority="low")],
                finish_reason="stop",
            ),
            answer("Done, added Milk."),
        ],
        model="openai/gpt-5",
    )
    assert send("add milk").json() == {"reply": "Done, added Milk."}
    assert [t["title"] for t in api.todos.values()] == ["Milk"]


def test_tool_error_is_reported_to_the_model(chat):
    send, _, model, _ = chat(
        [
            answer(tool_calls=[call("c1", "complete_todo", todo_id="does-not-exist")]),
            answer("I couldn't find that todo."),
        ]
    )
    assert send("finish my report").json()["reply"] == "I couldn't find that todo."
    result = model.requests[1]["messages"][-1]
    assert result["content"] == "error: todo not found"  # the api's own message


def test_bad_tool_arguments_are_reported_not_crashed(chat):
    broken_json = {"name": "create_todo", "arguments": "{oops"}
    bad = {"id": "c1", "type": "function", "function": broken_json}
    send, _, model, _ = chat([answer(tool_calls=[bad]), answer("Sorry, let me retry.")])
    assert send("add milk").status_code == 200
    assert model.requests[1]["messages"][-1]["content"].startswith("error: invalid arguments")


def test_runaway_loop_stops_at_max_steps(chat):
    send, _, model, _ = chat([])  # empty script → the fake keeps asking for tools forever
    res = send("loop please")
    assert res.status_code == 200
    assert "too many steps" in res.json()["reply"]
    assert len(model.requests) == 10  # agent_max_steps


def test_refusal(chat):
    send, _, _, _ = chat([answer(None, refusal="I can't help with that.")])
    assert send("something not allowed").json() == {"reply": "Sorry, I can't help with that."}


def test_cut_off_answer_says_so(chat):
    send, _, _, _ = chat([answer("Here is the start of", finish_reason="length")])
    assert "cut off" in send("write a lot").json()["reply"]


def test_llm_down_is_502_and_user_message_is_kept(chat):
    send, history, model, _ = chat([], always_fail=500)
    res = send("hello?")
    assert res.status_code == 502
    assert 2 <= len(model.requests) <= 5  # the SDK retried a few times, then gave up
    assert res.json()["error"] == "agent failed to respond"
    # Append-only: the user's message stays; the next message simply follows it.
    assert [m["role"] for m in history()] == ["user"]


def test_no_credits_is_502(chat):
    send, _, _, _ = chat([402])  # OpenRouter: "requires more credits"
    assert send("hello?").status_code == 502


def test_empty_message_is_400(chat):
    send, _, model, _ = chat([])
    res = send("   ")
    assert res.status_code == 400
    assert res.json()["error"] == "message is required"
    assert model.requests == []  # no money spent


def test_needs_a_token(db_client):
    res = db_client.post(CHAT, json={"message": "hi"})
    assert res.status_code == 401


def test_second_message_while_busy_is_409(chat, database_url):
    _, _, model, _ = chat([answer("hi")])
    token = make_token()
    user_id = jwt.decode(token, options={"verify_signature": False})["user_id"]

    # Pretend another message from this user is still being answered:
    # hold the same advisory lock from another connection.
    with psycopg.connect(database_url, autocommit=True) as other:
        other.execute("SELECT pg_advisory_lock(1, hashtext(%s))", (user_id,))
        res = TestClient(app).post(CHAT, json={"message": "hi"}, headers=auth(token))
        assert res.status_code == 409
        assert res.json()["error"] == "still answering your previous message"
    assert model.requests == []
