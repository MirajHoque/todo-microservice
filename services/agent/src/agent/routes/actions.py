"""routes/actions.py — the user's Confirm / Cancel clicks (step 2i.1).

POST   /api/v1/agent/actions/{id}/confirm → do it: delete the todos
DELETE /api/v1/agent/actions/{id}         → cancel: delete nothing

These are the ONLY way anything gets deleted. The model has no tool
that calls them — only a person clicking a button in web does. That's
what makes this a guardrail in code: no prompt, mistake or injected
text can delete a todo on its own.

Both answer {"reply": "..."} (shown in the chat like an agent message)
and add a short note to the conversation, so on the next message the
orchestrator knows what the user decided. 404 if the action doesn't
exist, belongs to someone else, was already used or has expired.
"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import actions, memory
from agent.auth import CurrentUser
from agent.db import Pool
from agent.log import get_logger
from agent.routes.chat import conversation_lock
from agent.todo_client import TodoAPIError, Todos

router = APIRouter(prefix="/api/v1/agent/actions")
log = get_logger(__name__)

NOT_FOUND = "this action is no longer available (it expired or was already used)"


class ActionResponse(BaseModel):
    reply: str


def _titles(todos: list[dict]) -> str:
    return ", ".join(f'"{t["title"]}"' for t in todos)


@router.post("/{action_id}/confirm")
async def confirm(
    action_id: uuid.UUID, caller: CurrentUser, pool: Pool, todos: Todos
) -> ActionResponse:
    async with conversation_lock(pool, caller.user_id) as conn:
        planned = await actions.take(conn, caller.user_id, str(action_id))
        if planned is None:
            raise HTTPException(404, NOT_FOUND)

        deleted, failed = [], []
        for todo in planned:
            try:
                await todos.delete_todo(caller, todo["id"])  # through the api, as the user
                deleted.append(todo)
            except TodoAPIError as exc:
                if exc.status == 404:  # already gone (deleted in the list meanwhile): fine
                    deleted.append(todo)
                else:
                    failed.append(todo)

        if deleted:
            reply = f"Deleted {_titles(deleted)}."
        else:
            reply = "Nothing was deleted."
        if failed:
            reply += f" Could not delete {_titles(failed)} — please try again."

        conversation_id = await memory.get_or_create_conversation(conn, caller.user_id)
        note = f"[app] The user pressed Confirm. {reply}"
        await memory.append_message(conn, conversation_id, {"role": "user", "content": note})

    log.info(
        "deletion confirmed",
        extra={"action": "delete_confirmed", "deleted": len(deleted), "failed": len(failed)},
    )
    return ActionResponse(reply=reply)


@router.delete("/{action_id}")
async def cancel(action_id: uuid.UUID, caller: CurrentUser, pool: Pool) -> ActionResponse:
    async with conversation_lock(pool, caller.user_id) as conn:
        planned = await actions.take(conn, caller.user_id, str(action_id))
        if planned is None:
            raise HTTPException(404, NOT_FOUND)

        reply = f"Okay, I kept {_titles(planned)}."
        conversation_id = await memory.get_or_create_conversation(conn, caller.user_id)
        note = f"[app] The user pressed Cancel. Nothing was deleted ({_titles(planned)} kept)."
        await memory.append_message(conn, conversation_id, {"role": "user", "content": note})

    log.info("deletion cancelled", extra={"action": "delete_cancelled"})
    return ActionResponse(reply=reply)
