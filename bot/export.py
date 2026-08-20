"""Export bot conversations to CSV/JSON.

Provides /export_conversations command for the owner.
"""

import csv
import io
import json
import logging
import time

from bot.stats import bot_stats

logger = logging.getLogger(__name__)


def export_json(days: int = 30) -> str:
    """Export recent conversations as a JSON string."""
    range_key = _days_to_range(days)
    records = bot_stats._filter_by_range(range_key)
    data = [
        {
            "question": r.question,
            "channel_id": r.channel_id,
            "confidence": r.confidence,
            "action": r.action,
            "latency_ms": r.latency_ms,
            "timestamp": r.timestamp,
        }
        for r in records
    ]
    return json.dumps(data, ensure_ascii=False, indent=2)


def export_csv(days: int = 30) -> str:
    """Export recent conversations as a CSV string."""
    range_key = _days_to_range(days)
    records = bot_stats._filter_by_range(range_key)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "question", "channel_id", "confidence", "action", "latency_ms"])

    for r in records:
        writer.writerow([
            r.timestamp,
            r.question,
            r.channel_id,
            r.confidence,
            r.action,
            r.latency_ms,
        ])

    return output.getvalue()


def export_count(days: int = 30) -> int:
    """Return the number of records that would be exported."""
    range_key = _days_to_range(days)
    return len(bot_stats._filter_by_range(range_key))


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
