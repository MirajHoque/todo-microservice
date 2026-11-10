"""todo_agent.py — the agent that manages todos with tool calls.

Works with ANY model on OpenRouter that supports tool calling — the
format below is OpenRouter's unified chat format, not one provider's.

How one chat message is handled (the "agent loop"):

  1. send the whole conversation + the tool definitions to the model
  2. the model answers. If its message has `tool_calls`, it asks us to
     run one or MORE tools; otherwise its text is the reply
  3. run every requested tool (in parallel) and add one
     {"role": "tool", "tool_call_id": ...} message per result, go to 1
  4. stop after agent_max_steps LLM calls, so a confused model can't
     loop (and spend money) forever

Every message — the model's (with tool_calls and reasoning_details) and
each tool result — is saved via `save(...)` the moment it exists. If
anything fails halfway, the stored history still matches what really
happened to the todos.

The tools don't touch a database: they call the api as the user
(todo_client.py). The model decides WHAT to do; the api decides
what's ALLOWED.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from openrouter import OpenRouter
from openrouter.components import ChatToolCall

from agent.auth import Caller
from agent.config import Settings
from agent.log import get_logger
from agent.todo_client import TodoAPIError, TodoClient

log = get_logger(__name__)

AGENT_NAME = "todo"

# save(message) — stores one message (see routes/chat.py)
SaveFn = Callable[[dict[str, Any]], Awaitable[None]]


class LLMError(Exception):
    """The model/provider failed in a way the SDK reports as a normal answer."""


SYSTEM_PROMPT = """You are a todo assistant inside a todo app. You manage the user's \
todo list with the tools provided; the tools act on this user's list only.

- Use the tools to actually make changes; only say something is done after the tool \
call succeeded.
- To complete or delete a todo you need its id. If you don't have it, call \
list_todos first and match by title.
- If a tool returns an error, explain it plainly and suggest what the user can do.
- Keep replies short and friendly. When listing todos, show title, priority and \
whether each is done; never show ids to the user."""


# ── Tool definitions (sent to the model on every call) ───────
# The model reads `description` to decide WHEN to use a tool and
# `parameters` (JSON Schema) to know WHAT to pass. strict +
# additionalProperties false: providers that support it guarantee
# the arguments match the schema exactly.


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
            "strict": True,
        },
    }


TODO_ID = {"todo_id": {"type": "string", "description": "The todo's id"}}

TOOLS: list[dict[str, Any]] = [
    _tool(
        "list_todos",
        "List all of the user's todos (id, title, priority, done). Use it to answer "
        "questions about the list, or to find a todo's id before changing it.",
        {},
        [],
    ),
    _tool(
        "create_todo",
        "Add a new todo for the user.",
        {
            "title": {"type": "string", "description": "What needs to be done"},
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "How urgent it is; medium if the user didn't say",
            },
        },
        ["title", "priority"],
    ),
    _tool("complete_todo", "Mark one of the user's todos as done.", TODO_ID, ["todo_id"]),
    _tool("delete_todo", "Permanently delete one of the user's todos.", TODO_ID, ["todo_id"]),
]


# ── Running a tool ───────────────────────────────────────────


async def run_tool(todos: TodoClient, caller: Caller, call: ChatToolCall) -> dict[str, Any]:
    """Run one tool call and return its {"role": "tool", ...} message.

    Failures are returned as text starting with "error:" (never dropped):
    the model reads the error and can explain it or try something else.
    """
    name = call.function.name
    start = time.perf_counter()
    ok = True
    try:
        args = json.loads(call.function.arguments or "{}")  # arguments arrive as a JSON string
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
        output = await _call(todos, caller, name, args)
    except TodoAPIError as exc:
        output, ok = f"error: {exc.message}", False
    except (KeyError, TypeError, ValueError) as exc:  # bad JSON, missing/odd arguments
        output, ok = f"error: invalid arguments for {name}: {exc}", False

    log.info(
        "tool call",
        extra={
            "action": "tool_call",
            "agent": AGENT_NAME,
            "tool": name,
            "ok": ok,
            "duration_ms": round((time.perf_counter() - start) * 1000),
        },
    )
    return {"role": "tool", "tool_call_id": call.id, "content": output}


async def _call(todos: TodoClient, caller: Caller, name: str, args: dict[str, Any]) -> str:
    """Do the actual work for one tool; returns text for the model to read."""
    match name:
        case "list_todos":
            items = await todos.list_todos(caller)
            if not items:
                return "The list is empty."
            return json.dumps([_summary(t) | {"done": t["done"]} for t in items])
        case "create_todo":
            t = await todos.create_todo(caller, args["title"], args.get("priority") or "medium")
            return json.dumps({"created": _summary(t)})
        case "complete_todo":
            t = await todos.update_todo(caller, args["todo_id"], done=True)
            return json.dumps({"completed": {"id": t["id"], "title": t["title"]}})
        case "delete_todo":
            await todos.delete_todo(caller, args["todo_id"])
            return json.dumps({"deleted": args["todo_id"]})
        case _:
            raise ValueError(f"unknown tool {name!r}")


def _summary(todo: dict[str, Any]) -> dict[str, Any]:
    """Just the fields the model needs (not timestamps, user ids, …)."""
    return {"id": todo["id"], "title": todo["title"], "priority": todo["priority"]}


def _text(content: Any) -> str:
    """Message content is usually a string, but may be a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


# ── The loop ─────────────────────────────────────────────────


async def run(
    llm: OpenRouter,
    todos: TodoClient,
    caller: Caller,
    history: list[dict[str, Any]],
    save: SaveFn,
    settings: Settings,
) -> str:
    """Answer the last user message in `history`. Returns the reply text."""
    messages = list(history)  # the full conversation, ending with the new user message

    for step in range(1, settings.agent_max_steps + 1):
        start = time.perf_counter()
        result = await llm.chat.send_async(
            model=settings.agent_model,
            # The system prompt isn't stored: always the current version.
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            tools=TOOLS,
            max_tokens=settings.llm_max_tokens,
            # How hard reasoning models think; ignored by models without it.
            reasoning_effort="medium",
        )
        if not result.choices:
            raise LLMError("the model returned no answer")
        choice = result.choices[0]
        usage = result.usage
        log.info(
            "llm call",
            extra={
                "action": "llm_call",
                "agent": AGENT_NAME,
                "model": result.model,  # the model that actually answered
                "step": step,
                "finish_reason": choice.finish_reason,
                "input_tokens": usage.prompt_tokens if usage else None,
                "output_tokens": usage.completion_tokens if usage else None,
                "cost_usd": usage.cost if usage else None,  # OpenRouter reports the real price
                "duration_ms": round((time.perf_counter() - start) * 1000),
            },
        )
        if choice.finish_reason == "error":
            raise LLMError("the model provider reported an error")

        # Store the model's message exactly as received — content,
        # tool_calls, reasoning_details. Append-only; replayed unchanged.
        reply_msg = choice.message
        assistant = reply_msg.model_dump(mode="json", by_alias=True, exclude_none=True)
        messages.append(assistant)
        await save(assistant)

        # Decide by the message, not finish_reason: some providers say
        # "stop" even when the message contains tool calls.
        if reply_msg.tool_calls:
            # Several tool calls in one turn: run them together.
            results = await asyncio.gather(
                *(run_tool(todos, caller, call) for call in reply_msg.tool_calls)
            )
            for tool_message in results:  # one message per result, in order
                messages.append(tool_message)
                await save(tool_message)
            continue

        if reply_msg.refusal or choice.finish_reason == "content_filter":
            return "Sorry, I can't help with that."

        reply = _text(reply_msg.content).strip()
        if choice.finish_reason == "length":
            reply += "\n\n(My answer was cut off. Please ask again more specifically.)"
        return reply or "Done."

    log.warning("agent hit max steps", extra={"action": "agent_max_steps", "agent": AGENT_NAME})
    return "Sorry, that took too many steps. Please try a simpler request."
