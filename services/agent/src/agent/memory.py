"""memory.py — read and clear a user's conversation in agent_db.

All SQL for the conversations/messages tables lives here (like the
repository files in services/api/internal/db/). Every function takes
the user_id from the verified JWT, so a user can only ever reach
their own conversation.

2e adds saving new messages; this step only reads and clears.
"""

from datetime import datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


async def get_messages(pool: AsyncConnectionPool, user_id: str) -> list[dict[str, Any]]:
    """All messages of the user's conversation, oldest first ([] if none)."""
    async with pool.connection() as conn:
        # dict_row: each row comes back as {"role": ..., "content": ...}
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(
            """
            SELECT m.role, m.content, m.created_at
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE c.user_id = %s
            ORDER BY m.id
            """,
            (user_id,),  # %s placeholders: psycopg sends values separately — no SQL injection
        )
        return await cur.fetchall()


async def clear(pool: AsyncConnectionPool, user_id: str) -> bool:
    """Delete the user's conversation (messages go with it: ON DELETE CASCADE).

    Returns True if there was something to delete.
    """
    async with pool.connection() as conn:
        cur = await conn.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
        return cur.rowcount > 0


def as_timestamp(value: datetime) -> str:
    return value.isoformat()
