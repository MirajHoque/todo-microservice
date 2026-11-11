"""routes/chat.py — POST /api/v1/agent/chat.

  request  {"message": "add buy milk"}
  response {"reply": "Added \"Buy milk\" to your list."}

+ "pending_action": {...} when the agent proposed deleting todos (step
2i.1): web shows Confirm / Cancel, and only the user's click deletes
(routes/actions.py).

Steps for one message:
  1. lock the user's conversation (one message at a time per user)
  2. check the user's rate limit and daily cost cap (usage.py) → 429
  3. load the stored history, append the new user message
  4. run the orchestrator (agents/orchestrator.py); it may hand work
     to the todo or planner agent, and saves each new message
  5. record what the LLM calls cost — even if the run failed
  6. store any proposed deletion as a pending action
  7. unlock, return the reply

Why the lock: if two messages from the same user ran at once, their
messages would interleave in the history (a tool_use from one run
followed by the other run's text) — a broken conversation. A
Postgres advisory lock works across ALL copies of this service, so it
still holds on Kubernetes with several replicas.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, HTTPException
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from agent import actions, memory, usage
from agent.agents import orchestrator
from agent.agents.loop import LLM_FAILURES, Budget, Run
from agent.auth import CurrentUser
from agent.config import get_settings
from agent.db import Pool
from agent.llm import LLM
from agent.log import get_logger
from agent.todo_client import Todos

router = APIRouter(prefix="/api/v1/agent")
log = get_logger(__name__)

CHAT_LOCK_SPACE = 1  # advisory locks are (space, key) pairs; 1 = chat, key = user


class ChatRequest(BaseModel):
    message: str


class TodoRef(BaseModel):
    id: str
    title: str


class PendingAction(BaseModel):
    """A deletion waiting for the user's Confirm / Cancel click."""

    id: str
    kind: str = "delete_todos"
    todos: list[TodoRef]
    expires_at: datetime


class ChatResponse(BaseModel):
    reply: str
    pending_action: PendingAction | None = None


@asynccontextmanager
async def conversation_lock(
    pool: AsyncConnectionPool, user_id: str
) -> AsyncIterator[AsyncConnection]:
    """One connection holding the user's conversation lock; 409 if it's taken.

    Used by the chat AND by Confirm/Cancel (routes/actions.py): both
    append to the conversation, so they must never run at the same time.
    """
    async with pool.connection() as conn:  # the advisory lock belongs to this connection
        cur = await conn.execute(
            "SELECT pg_try_advisory_lock(%s, hashtext(%s))", (CHAT_LOCK_SPACE, user_id)
        )
        if not (await cur.fetchone())[0]:
            raise HTTPException(409, "still answering your previous message")
        try:
            yield conn
        finally:
            await conn.execute(
                "SELECT pg_advisory_unlock(%s, hashtext(%s))", (CHAT_LOCK_SPACE, user_id)
            )


@router.post("/chat", response_model_exclude_none=True)  # no pending_action → field left out
async def chat(
    body: ChatRequest, caller: CurrentUser, pool: Pool, todos: Todos, llm: LLM
) -> ChatResponse:
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "message is required")  # same message as the Go api
    if len(text) > 4000:
        raise HTTPException(400, "message is too long (max 4000 characters)")

    settings = get_settings()
    async with conversation_lock(pool, caller.user_id) as conn:
        # Guardrail (2i.2): over a limit → 429 before any model is called.
        try:
            await usage.check_and_count(conn, caller.user_id, settings)
        except usage.LimitReached as exc:
            log.warning("limit reached", extra={"action": "rate_limited", "error": exc.message})
            # Retry-After: the standard header saying how many seconds to wait.
            raise HTTPException(
                429, exc.message, headers={"Retry-After": str(exc.retry_after)}
            ) from None

        run = Run(
            llm=llm,
            settings=settings,
            todos=todos,
            caller=caller,
            # One budget for ALL agents working on this message.
            budget=Budget(settings.agent_max_steps),
        )
        try:
            conversation_id = await memory.get_or_create_conversation(conn, caller.user_id)
            history = await memory.load_history(conn, conversation_id)

            user_message = {"role": "user", "content": text}
            await memory.append_message(conn, conversation_id, user_message)
            history.append(user_message)

            async def save(message: dict) -> None:
                await memory.append_message(conn, conversation_id, message)

            reply = await orchestrator.run(run, history, save)
        except LLM_FAILURES as exc:  # the orchestrator's own model call failed
            log.error("llm call failed", extra={"action": "llm_fail", "error": str(exc)[:300]})
            raise HTTPException(502, "agent failed to respond") from None  # Go api's message
        finally:
            # Calls that happened cost money even if the run failed halfway.
            await usage.add_cost(conn, caller.user_id, run.llm_calls, run.cost_usd)

        pending = None
        if run.pending_deletes:  # the agent proposed deletions: wait for the user's click
            action_id, expires_at = await actions.propose_deletion(
                conn, conversation_id, run.pending_deletes
            )
            pending = PendingAction(id=action_id, todos=run.pending_deletes, expires_at=expires_at)
            log.info(
                "deletion waiting for confirmation",
                extra={"action": "delete_proposed", "todos": len(run.pending_deletes)},
            )

    return ChatResponse(reply=reply, pending_action=pending)
