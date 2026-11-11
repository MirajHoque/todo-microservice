"""usage.py — per-user rate limit and daily cost cap (step 2i.2).

A guardrail in code: before a chat message reaches any model, we check
what this user already used:

  - messages this hour >= CHAT_MESSAGES_PER_HOUR → 429, try next hour
  - AI cost today      >= DAILY_COST_LIMIT_USD   → 429, try tomorrow

Counted in Postgres (the `usage` table), not in memory: on Kubernetes
several copies of this service answer requests, and they must all see
the same numbers. Logging out doesn't reset anything.

Fixed windows: "this hour" means 14:00–14:59, not "the last 60
minutes". Simple and cheap — the trade-off is that someone could send
30 messages at 14:59 and 30 more at 15:00.

The cost cap is checked BEFORE a message, but the cost is only known
AFTER (OpenRouter reports it per call). So the last message of the day
can go a little over — at most one message, which the step budget
(AGENT_MAX_STEPS) keeps small.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from agent.config import Settings


class LimitReached(Exception):
    """The user hit a limit; `retry_after` = seconds until it resets."""

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


def money(usd: float) -> str:
    """$0.50, but $0.006 stays $0.006 (2 decimals would round it to $0.01)."""
    return f"${usd:.2f}" if round(usd, 2) == usd else f"${usd:.6f}".rstrip("0")


@dataclass
class Usage:
    messages_this_hour: int
    cost_today_usd: float


async def get(conn: AsyncConnection, user_id: str) -> Usage:
    """What the user used in the current hour (messages) and today (cost)."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        SELECT
          COALESCE(SUM(messages) FILTER (WHERE hour = date_trunc('hour', now())), 0) AS messages,
          COALESCE(SUM(cost_usd), 0) AS cost
        FROM usage
        -- since midnight UTC, whatever time zone the database server uses
        WHERE user_id = %s AND hour >= date_trunc('day', now(), 'UTC')
        """,
        (user_id,),
    )
    row = await cur.fetchone()
    return Usage(messages_this_hour=int(row["messages"]), cost_today_usd=float(row["cost"]))


async def check_and_count(conn: AsyncConnection, user_id: str, settings: Settings) -> None:
    """Raise LimitReached if the user is over a limit; otherwise count this message.

    Called while the user's conversation lock is held (routes/chat.py), so
    two messages of the same user can't both pass the check at once.
    """
    used = await get(conn, user_id)
    now = datetime.now(UTC)

    if used.cost_today_usd >= settings.daily_cost_limit_usd:
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        raise LimitReached(
            f"daily AI budget used up ({money(settings.daily_cost_limit_usd)}); try again tomorrow",
            retry_after=int((tomorrow - now).total_seconds()) + 1,
        )

    if used.messages_this_hour >= settings.chat_messages_per_hour:
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        wait = int((next_hour - now).total_seconds()) + 1
        raise LimitReached(
            f"too many messages: the limit is {settings.chat_messages_per_hour} per hour; "
            f"try again in {wait // 60 + 1} min",
            retry_after=wait,
        )

    await conn.execute(
        """
        INSERT INTO usage (user_id, hour, messages) VALUES (%s, date_trunc('hour', now()), 1)
        ON CONFLICT (user_id, hour) DO UPDATE SET messages = usage.messages + 1
        """,
        (user_id,),
    )


async def add_cost(conn: AsyncConnection, user_id: str, llm_calls: int, cost_usd: float) -> None:
    """Add what one chat message's LLM calls cost (all agents together)."""
    if not llm_calls:
        return
    await conn.execute(
        """
        INSERT INTO usage (user_id, hour, llm_calls, cost_usd)
        VALUES (%s, date_trunc('hour', now()), %s, %s)
        ON CONFLICT (user_id, hour) DO UPDATE
          SET llm_calls = usage.llm_calls + EXCLUDED.llm_calls,
              cost_usd = usage.cost_usd + EXCLUDED.cost_usd
        """,
        (user_id, llm_calls, cost_usd),
    )
