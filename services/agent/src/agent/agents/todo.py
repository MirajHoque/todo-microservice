"""agents/todo.py — the todo agent: the only agent that CHANGES todos.

It never talks to the user. The orchestrator hands it one task
("Create 'Buy milk' with priority high") and gets back a short
factual report — including todo ids, so the orchestrator can say
"mark [id: …] as done" next time without another lookup.

Every task starts from an empty conversation: the task text must say
everything (the orchestrator's prompt tells it so). The conversation
memory lives with the orchestrator.

The tools don't touch a database: they call the api as the user
(todo_client.py). The model decides WHAT to do; the api decides
what's ALLOWED.

Guardrail (step 2i.1): delete_todo does NOT delete. It only proposes;
the user must press Confirm in the app (actions.py). This agent has no
way to confirm, so a mistake or an injected instruction can't delete.
"""

import json
from typing import Any

from agent.agents.loop import Agent, Run, Tool

SYSTEM_PROMPT = """You are the todo agent inside a todo app. You get one task from the \
orchestrator (another AI agent), never from the user directly. You manage this user's \
todo list with your tools; they act on this user's list only.

- Do the task with the tools. Only report something as done after the tool call succeeded.
- When the task involves several todos, call the tools for all of them in the same \
turn (they run in parallel), not one per turn.
- To complete or delete a todo you need its id. If the task doesn't give it, call \
list_todos first and match by title.
- If the task is unclear (for example two todos match), change nothing and say what is \
unclear.
- delete_todo only asks the user: the app shows them a Confirm button, and the todo is \
deleted only if they press it. Report such todos as "waiting for the user to confirm", \
never as deleted.
- Finish with a short factual report of what you did: titles, priorities, done or not, \
and each todo's id as [id: ...] so the orchestrator can refer to it later. Report \
errors exactly as the tool returned them."""


# ── The tools' Python side ───────────────────────────────────


def _summary(todo: dict[str, Any]) -> dict[str, Any]:
    """Just the fields a model needs (not timestamps, user ids, …)."""
    return {"id": todo["id"], "title": todo["title"], "priority": todo["priority"]}


async def _list_todos(run: Run, args: dict[str, Any]) -> str:
    items = await run.todos.list_todos(run.caller)
    if not items:
        return "The list is empty."
    return json.dumps([_summary(t) | {"done": t["done"]} for t in items])


async def _create_todo(run: Run, args: dict[str, Any]) -> str:
    priority = args.get("priority") or "medium"
    todo = await run.todos.create_todo(run.caller, args["title"], priority)
    return json.dumps({"created": _summary(todo)})


async def _complete_todo(run: Run, args: dict[str, Any]) -> str:
    todo = await run.todos.update_todo(run.caller, args["todo_id"], done=True)
    return json.dumps({"completed": {"id": todo["id"], "title": todo["title"]}})


async def _delete_todo(run: Run, args: dict[str, Any]) -> str:
    """Propose a deletion — the user confirms it in the app (or not)."""
    todo_id = args["todo_id"]
    # Look it up: a wrong id fails now, and the button can show the title.
    todo = next((t for t in await run.todos.list_todos(run.caller) if t["id"] == todo_id), None)
    if todo is None:
        return "error: todo not found"
    if all(p["id"] != todo_id for p in run.pending_deletes):
        run.pending_deletes.append({"id": todo_id, "title": todo["title"]})
    return json.dumps(
        {
            "waiting_for_user": {"id": todo_id, "title": todo["title"]},
            "note": "NOT deleted. The app shows the user a Confirm button; "
            "it is deleted only if they press it.",
        }
    )


# ── Tool definitions ─────────────────────────────────────────

TODO_ID = {"todo_id": {"type": "string", "description": "The todo's id"}}

# Read-only: also given to the planner (planner.py).
LIST_TODOS = Tool(
    "list_todos",
    "List all of the user's todos (id, title, priority, done). Use it to answer "
    "questions about the list, or to find a todo's id before changing it.",
    {},
    _list_todos,
)

AGENT = Agent(
    name="todo",
    system_prompt=SYSTEM_PROMPT,
    reasoning_effort="low",  # simple, clear tasks: little thinking needed
    tools=(
        LIST_TODOS,
        Tool(
            "create_todo",
            "Add a new todo for the user.",
            {
                "title": {"type": "string", "description": "What needs to be done"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "How urgent it is; medium if not given",
                },
            },
            _create_todo,
            required=("title", "priority"),
        ),
        Tool(
            "complete_todo",
            "Mark one of the user's todos as done.",
            TODO_ID,
            _complete_todo,
            required=("todo_id",),
        ),
        Tool(
            "delete_todo",
            "Ask to delete one of the user's todos. It is NOT deleted right away: the app "
            "shows the user a Confirm button, and only their click deletes it.",
            TODO_ID,
            _delete_todo,
            required=("todo_id",),
        ),
    ),
)


async def run(run: Run, task: str) -> str:
    """Do one task for the orchestrator; returns the agent's report."""
    return await AGENT.run(run, [{"role": "user", "content": task}])
