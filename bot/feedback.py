"""User satisfaction feedback — 👍/👎 reactions on bot replies.

Tracks satisfaction rate and flags low-satisfaction answers for review.
Persisted to ``data/feedback.json``.
"""

import json
import logging
import os
import time

from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

FEEDBACK_FILE = data_path(os.getenv("FEEDBACK_FILE", "data/feedback.json"))
_MAX_RECORDS = 500


def _load() -> list[dict]:
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save(data: list[dict]) -> None:
    atomic_json_write(FEEDBACK_FILE, data[-_MAX_RECORDS:], ensure_ascii=False, indent=2)


def record_feedback(
    message_id: int,
    channel_id: int,
    user_id: int,
    question: str,
    answer: str,
    is_positive: bool,
) -> None:
    """Record a 👍 or 👎 feedback event."""
    records = _load()
    # Prevent duplicate feedback from same user on same message
    for r in records:
        if r.get("message_id") == message_id and r.get("user_id") == user_id:
            r["is_positive"] = is_positive
            r["timestamp"] = time.time()
            _save(records)
            return
    records.append({
        "message_id": message_id,
        "channel_id": channel_id,
        "user_id": user_id,
        "question": question[:300],
        "answer": answer[:300],
        "is_positive": is_positive,
        "timestamp": time.time(),
    })
    _save(records)
    logger.info("Feedback recorded: msg=%d positive=%s", message_id, is_positive)


def satisfaction_stats(days: int = 30) -> dict:
    """Return satisfaction statistics for the last *days* days."""
    records = _load()
    cutoff = time.time() - days * 86400
    recent = [r for r in records if r.get("timestamp", 0) >= cutoff]
    total = len(recent)
    positive = sum(1 for r in recent if r.get("is_positive"))
    negative = total - positive
    rate = round(positive / total * 100, 1) if total else 0.0
    return {
        "total": total,
        "positive": positive,
        "negative": negative,
        "satisfaction_rate": rate,
    }


def low_satisfaction_answers(limit: int = 10) -> list[dict]:
    """Return recent negatively-rated answers."""
    records = _load()
    negatives = [r for r in records if not r.get("is_positive")]
    negatives.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
    return negatives[:limit]
