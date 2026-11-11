"""routes/usage.py — GET /api/v1/agent/usage: how close am I to my limits?

  {"messages_this_hour": 3, "messages_per_hour": 30,
   "cost_today_usd": 0.0412, "daily_cost_limit_usd": 0.5}

Read-only; the limits themselves are enforced in routes/chat.py (usage.py).
"""

from fastapi import APIRouter
from pydantic import BaseModel

from agent import usage
from agent.auth import CurrentUser
from agent.config import get_settings
from agent.db import Pool

router = APIRouter(prefix="/api/v1/agent")


class UsageResponse(BaseModel):
    messages_this_hour: int
    messages_per_hour: int
    cost_today_usd: float
    daily_cost_limit_usd: float


@router.get("/usage")
async def get_usage(caller: CurrentUser, pool: Pool) -> UsageResponse:
    settings = get_settings()
    async with pool.connection() as conn:
        used = await usage.get(conn, caller.user_id)
    return UsageResponse(
        messages_this_hour=used.messages_this_hour,
        messages_per_hour=settings.chat_messages_per_hour,
        cost_today_usd=round(used.cost_today_usd, 6),
        daily_cost_limit_usd=settings.daily_cost_limit_usd,
    )
