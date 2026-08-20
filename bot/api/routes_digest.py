"""Digest API route — returns latest 24h activity summary."""

import time

from fastapi import APIRouter, Depends

from bot.api.auth import get_current_user
from bot.stats import bot_stats

router = APIRouter(prefix="/api/digest", tags=["digest"])


@router.get("")
async def get_digest(_user: str = Depends(get_current_user)) -> dict:
    """Return a 24h activity digest."""
    cutoff = time.time() - 86400  # 24 hours
    recent = [r for r in bot_stats.recent if r.timestamp >= cutoff]

    if not recent:
        return {
            "total": 0,
            "auto_replies": 0,
            "forwards": 0,
            "avg_confidence": 0,
            "avg_latency_ms": 0,
            "top_channels": {},
            "queries": [],
        }

    auto = sum(1 for r in recent if r.action == "auto_reply")
    forwards = len(recent) - auto
    avg_conf = sum(r.confidence for r in recent) / len(recent)
    avg_lat = sum(r.latency_ms for r in recent) / len(recent)

    channel_counts: dict[int, int] = {}
    for r in recent:
        channel_counts[r.channel_id] = channel_counts.get(r.channel_id, 0) + 1

    queries = [
        {
            "question": r.question[:100],
            "channel_id": r.channel_id,
            "confidence": r.confidence,
            "action": r.action,
            "latency_ms": r.latency_ms,
            "timestamp": r.timestamp,
        }
        for r in recent[-20:]
    ]

    return {
        "total": len(recent),
        "auto_replies": auto,
        "forwards": forwards,
        "avg_confidence": round(avg_conf, 1),
        "avg_latency_ms": round(avg_lat, 0),
        "top_channels": channel_counts,
        "queries": queries,
    }
