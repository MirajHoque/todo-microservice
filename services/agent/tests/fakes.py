"""fakes.py — a fake model and a fake todo api for the agent tests.

The real OpenRouter SDK and the real TodoClient are used — only the
network is replaced (MockTransport):

  FakeModel   answers from one script PER AGENT, in OpenRouter's chat
              format. It knows which agent is calling from the system
              prompt, and records every request
  FakeTodoAPI keeps todos in a dict, like the todo service would

The `chat` fixture (conftest.py) swaps both into the app.
"""

import json
from typing import Any

import httpx
import httpx2
from openrouter import OpenRouter

from agent.agents import orchestrator, planner, todo
from agent.config import get_settings
from agent.llm import create_llm
from agent.todo_client import TodoClient

CHAT = "/api/v1/agent/chat"
CONVERSATION = "/api/v1/agent/conversation"

PROMPTS = {
    orchestrator.SYSTEM_PROMPT: "orchestrator",
    todo.SYSTEM_PROMPT: "todo",
    planner.SYSTEM_PROMPT: "planner",
}


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


# What each agent does when its script is empty: call a tool again,
# forever (to test the step budget).
LOOP_FOREVER = {
    "orchestrator": lambda: call("loop", "delegate_to_todo_agent", task="list my todos"),
    "todo": lambda: call("loop", "list_todos"),
    "planner": lambda: call("loop", "list_todos"),
}


class FakeModel:
    """Plays OpenRouter's /chat/completions.

    scripts: {"orchestrator": [...], "todo": [...], "planner": [...]} —
    each entry is one answer (from `answer(...)`), or an int to fail with
    that HTTP status. fail: {"todo": 500} makes every call of that agent fail.
    """

    def __init__(self, model: str = "anthropic/claude-sonnet-5.5", fail=None, **scripts) -> None:
        self.scripts = {name: list(s) for name, s in scripts.items()}
        self.model = model
        self.fail = fail or {}
        self.requests: list[tuple[str, dict]] = []  # (agent, request body), in order

    def calls(self, agent: str) -> list[dict]:
        """The request bodies one agent sent."""
        return [body for name, body in self.requests if name == agent]

    def handler(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        system = body["messages"][0]["content"]  # who is asking? (+ maybe the wrap-up note)
        agent = next(name for prompt, name in PROMPTS.items() if system.startswith(prompt))
        self.requests.append((agent, body))
        if agent in self.fail:
            return httpx.Response(self.fail[agent], json={"error": {"message": "provider down"}})
        script = self.scripts.get(agent, [])
        step = script.pop(0) if script else answer(tool_calls=[LOOP_FOREVER[agent]()])
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
    """Plays the todo service's /api/v1/todos endpoints, in memory."""

    def __init__(self) -> None:
        self.todos: dict[str, dict] = {}
        self.seen: list[tuple[str, str]] = []  # (method, authorization header)

    def handler(self, req: httpx2.Request) -> httpx2.Response:
        self.seen.append((req.method, req.headers.get("authorization", "")))
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


def roles(messages: list[dict]) -> list[str]:
    return [m["role"] for m in messages]
