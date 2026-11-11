"""routes/conversation.py — the caller's chat history.

GET    /api/v1/agent/conversation → the saved messages (oldest first)
DELETE /api/v1/agent/conversation → forget them (called on logout, 2f)

Both need a valid JWT: `caller: CurrentUser` makes FastAPI run the
token check (auth.py) before the handler. No token → 401, and the
handler never runs. The user id comes from the token, never from the
URL or body — so nobody can read someone else's conversation.
"""

import logging
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel

from agent import memory
from agent.auth import CurrentUser
from agent.db import Pool

router = APIRouter(prefix="/api/v1/agent")  # prefix: every route below starts with this
log = logging.getLogger(__name__)


class Message(BaseModel):
    role: str  # "user" | "assistant" | "tool"
    message: dict[str, Any]  # the full message in OpenRouter's chat format
    created_at: str


class ConversationResponse(BaseModel):
    messages: list[Message]


@router.get("/conversation")
async def get_conversation(caller: CurrentUser, pool: Pool) -> ConversationResponse:
    rows = await memory.get_messages(pool, caller.user_id)
    return ConversationResponse(
        messages=[
            Message(
                role=r["role"],
                message=r["message"],
                created_at=memory.as_timestamp(r["created_at"]),
            )
            for r in rows
        ]
    )


@router.delete("/conversation", status_code=204)
async def delete_conversation(caller: CurrentUser, pool: Pool) -> Response:
    deleted = await memory.clear(pool, caller.user_id)
    log.info("conversation cleared", extra={"action": "memory_clear", "deleted": deleted})
    return Response(status_code=204)  # 204 No Content — like DELETE in the api
