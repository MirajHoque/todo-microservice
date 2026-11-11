"""actions.py — actions that wait for the user's click (human-in-the-loop).

A guardrail in code, not in the prompt: the delete_todo tool can only
PROPOSE a deletion (it lands in Run.pending_deletes). After the chat
message, the proposal is stored here and sent to web, which shows
Confirm / Cancel buttons. Only the user's click — a separate HTTP
request the model can't make (routes/actions.py) — deletes anything.

All SQL for the pending_actions table lives here (like memory.py).
"""

from datetime import datetime, timedelta
from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

EXPIRES_AFTER = timedelta(minutes=10)  # an old button stops working


async def propose_deletion(
    conn: AsyncConnection, conversation_id: str, todos: list[dict[str, Any]]
) -> tuple[str, datetime]:
    """Store a deletion waiting for the user; replaces an older one.

    Returns (action id, expires_at).
    """
    cur = await conn.execute(
        """
        INSERT INTO pending_actions (conversation_id, kind, todos, expires_at)
        VALUES (%s, 'delete_todos', %s, now() + %s)
        ON CONFLICT (conversation_id) DO UPDATE
            SET id = gen_random_uuid(), todos = EXCLUDED.todos,
                created_at = now(), expires_at = EXCLUDED.expires_at
        RETURNING id, expires_at
        """,
        (conversation_id, Jsonb(todos), EXPIRES_AFTER),
    )
    action_id, expires_at = await cur.fetchone()
    return str(action_id), expires_at


async def take(conn: AsyncConnection, user_id: str, action_id: str) -> list[dict] | None:
    """Remove the user's pending action and return its todos (None if not found).

    DELETE … RETURNING does "find + remove" in one step, so a double
    click (or two browser tabs) can't run the same action twice. The
    user_id check means nobody can confirm someone else's action, and
    expired actions are simply not found.
    """
    cur = await conn.execute(
        """
        DELETE FROM pending_actions p
        USING conversations c
        WHERE p.id = %s AND p.conversation_id = c.id
          AND c.user_id = %s AND p.expires_at > now()
        RETURNING p.todos
        """,
        (action_id, user_id),
    )
    row = await cur.fetchone()
    return row[0] if row else None
