"""routes/chat.py — POST /api/v1/agent/chat.

Same contract as the Go api's endpoint, so web needs no change:
  request  {"message": "add buy milk"}
  response {"reply": "Added \"Buy milk\" to your list."}

Steps for one message:
  1. lock the user's conversation (one message at a time per user)
  2. load the stored history, append the new user message
  3. run the orchestrator (agents/orchestrator.py); it may hand work
     to the todo or planner agent, and saves each new message
  4. unlock, return the reply

Why the lock: if two messages from the same user ran at once, their
messages would interleave in the history (a tool_use from one run
followed by the other run's text) — a broken conversation. A
Postgres advisory lock works across ALL copies of this service, so it
still holds on Kubernetes with several replicas.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import memory
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


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat")
async def chat(
    body: ChatRequest, caller: CurrentUser, pool: Pool, todos: Todos, llm: LLM
) -> ChatResponse:
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "message is required")  # same message as the Go api
    if len(text) > 4000:
        raise HTTPException(400, "message is too long (max 4000 characters)")

    # One connection for the whole chat: the advisory lock belongs to it.
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT pg_try_advisory_lock(%s, hashtext(%s))", (CHAT_LOCK_SPACE, caller.user_id)
        )
        if not (await cur.fetchone())[0]:
            raise HTTPException(409, "still answering your previous message")
        try:
            conversation_id = await memory.get_or_create_conversation(conn, caller.user_id)
            history = await memory.load_history(conn, conversation_id)

            user_message = {"role": "user", "content": text}
            await memory.append_message(conn, conversation_id, user_message)
            history.append(user_message)

            async def save(message: dict) -> None:
                await memory.append_message(conn, conversation_id, message)

            settings = get_settings()
            run = Run(
                llm=llm,
                settings=settings,
                todos=todos,
                caller=caller,
                # One budget for ALL agents working on this message.
                budget=Budget(settings.agent_max_steps),
            )
            reply = await orchestrator.run(run, history, save)
        except LLM_FAILURES as exc:  # the orchestrator's own model call failed
            log.error("llm call failed", extra={"action": "llm_fail", "error": str(exc)[:300]})
            raise HTTPException(502, "agent failed to respond") from None  # Go api's message
        finally:
            await conn.execute(
                "SELECT pg_advisory_unlock(%s, hashtext(%s))", (CHAT_LOCK_SPACE, caller.user_id)
            )

    return ChatResponse(reply=reply)
