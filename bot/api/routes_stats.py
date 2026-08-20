"""Stats API routes."""

from fastapi import APIRouter, Depends

from bot.api.auth import get_current_user
from bot.health import uptime_seconds
from bot.stats import bot_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
async def get_stats(_user: str = Depends(get_current_user)) -> dict:
    """Return bot statistics snapshot with recent queries."""
    snap = bot_stats.snapshot()
    snap["uptime_seconds"] = round(uptime_seconds(), 1)
    snap["recent"] = bot_stats.top_questions(20)
    return snap
