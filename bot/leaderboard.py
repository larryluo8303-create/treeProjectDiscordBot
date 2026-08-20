"""Leaderboard — most active questioners & most-referenced KB docs.

Uses data from bot_stats to compute rankings.
"""

import logging
from collections import Counter

from bot.stats import bot_stats

logger = logging.getLogger(__name__)


def top_questioners(limit: int = 10, days: int = 30) -> list[dict]:
    """Return the most active users by query count in the last *days* days.

    Returns list of ``{user_id, count}`` (user_id from channel context).
    Note: stats track channel_id not user_id directly, so this returns
    top channels as a proxy.
    """
    range_key = _days_to_range(days)
    records = bot_stats._filter_by_range(range_key)
    counter: Counter[int] = Counter()
    for r in records:
        counter[r.channel_id] += 1
    return [
        {"channel_id": cid, "count": count}
        for cid, count in counter.most_common(limit)
    ]


def top_questions_by_frequency(limit: int = 10, days: int = 30) -> list[dict]:
    """Return most frequently asked questions (by exact match, truncated)."""
    range_key = _days_to_range(days)
    records = bot_stats._filter_by_range(range_key)
    counter: Counter[str] = Counter()
    for r in records:
        q = r.question.strip()[:100].lower()
        if q:
            counter[q] += 1
    return [
        {"question": q, "count": count}
        for q, count in counter.most_common(limit)
    ]


def confidence_distribution(days: int = 30) -> dict[str, int]:
    """Return confidence score distribution buckets."""
    range_key = _days_to_range(days)
    records = bot_stats._filter_by_range(range_key)
    buckets = {"1-3": 0, "4-6": 0, "7-8": 0, "9-10": 0}
    for r in records:
        c = r.confidence
        if c <= 3:
            buckets["1-3"] += 1
        elif c <= 6:
            buckets["4-6"] += 1
        elif c <= 8:
            buckets["7-8"] += 1
        else:
            buckets["9-10"] += 1
    return buckets


def _days_to_range(days: int) -> str:
    if days <= 1:
        return "24h"
    elif days <= 7:
        return "7d"
    elif days <= 30:
        return "30d"
    elif days <= 90:
        return "90d"
    elif days <= 365:
        return "365d"
    return "all"
