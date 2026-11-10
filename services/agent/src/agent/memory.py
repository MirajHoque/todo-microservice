"""memory.py — a user's conversation in agent_db.

All SQL for the conversations/messages tables lives here (like the
repository files in services/api/internal/db/). Every function takes
the user_id from the verified JWT, so a user can only ever reach
their own conversation.

Each row is ONE message in OpenRouter's chat format, stored EXACTLY as
sent to / received from the model (see migration 003):
  {"role": "user", "content": "..."}
  {"role": "assistant", "content": "...", "tool_calls": [...], "reasoning_details": [...]}
  {"role": "tool", "tool_call_id": "...", "content": "..."}

History is APPEND-ONLY: we never edit, reorder or trim earlier messages.
  - tool calls and results are kept → the model remembers what it
    actually did (the Go agent dropped them: the 1c.6 bug)
  - reasoning_details are replayed unchanged; models that "think"
    (like Claude) need them to continue across tool calls
"""

from datetime import datetime
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

ChatMessage = dict[str, Any]  # one message in OpenRouter's chat format


async def get_messages(pool: AsyncConnectionPool, user_id: str) -> list[dict[str, Any]]:
    """All messages of the user's conversation, oldest first ([] if none)."""
    async with pool.connection() as conn:
        # dict_row: each row comes back as {"role": ..., "message": ...}
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(
            """
            SELECT m.role, m.message, m.created_at
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE c.user_id = %s
            ORDER BY m.id
            """,
            (user_id,),  # %s placeholders: psycopg sends values separately — no SQL injection
        )
        return await cur.fetchall()


async def load_history(conn: AsyncConnection, conversation_id: str) -> list[ChatMessage]:
    """The conversation as the `messages` list for the next LLM call."""
    cur = await conn.execute(
        "SELECT message FROM messages WHERE conversation_id = %s ORDER BY id",
        (conversation_id,),
    )
    return [row[0] for row in await cur.fetchall()]


async def get_or_create_conversation(conn: AsyncConnection, user_id: str) -> str:
    """The user's conversation id, creating the conversation on first use."""
    # ON CONFLICT … DO UPDATE … RETURNING: one statement that works whether
    # or not the row exists yet (user_id is UNIQUE).
    cur = await conn.execute(
        """
        INSERT INTO conversations (user_id) VALUES (%s)
        ON CONFLICT (user_id) DO UPDATE SET updated_at = now()
        RETURNING id
        """,
        (user_id,),
    )
    row = await cur.fetchone()
    return str(row[0])


async def append_message(conn: AsyncConnection, conversation_id: str, message: ChatMessage) -> None:
    """Add one message at the end. Never edits earlier ones (append-only)."""
    await conn.execute(
        "INSERT INTO messages (conversation_id, role, message) VALUES (%s, %s, %s)",
        (conversation_id, message["role"], Jsonb(message)),
    )


async def clear(pool: AsyncConnectionPool, user_id: str) -> bool:
    """Delete the user's conversation (messages go with it: ON DELETE CASCADE).

    Returns True if there was something to delete.
    """
    async with pool.connection() as conn:
        cur = await conn.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
        return cur.rowcount > 0


def as_timestamp(value: datetime) -> str:
    return value.isoformat()
