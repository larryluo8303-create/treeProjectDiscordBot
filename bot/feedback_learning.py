"""Feedback-to-ingestion learning loop helpers."""

import json
import os
import re
import time

from bot.utils import atomic_json_write, data_path

LEARNING_QUEUE_FILE = data_path(os.getenv("LEARNING_QUEUE_FILE", "data/learning_queue.json"))
LEARNING_REPORT_STATE_FILE = data_path(os.getenv("LEARNING_REPORT_STATE_FILE", "data/learning_report_state.json"))


def _load(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _save(path: str, data) -> None:
    atomic_json_write(path, data, ensure_ascii=False, indent=2)


def _normalize_question(question: str) -> str:
    q = (question or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q[:200]


def record_gap_question(question: str, source: str) -> None:
    q = _normalize_question(question)
    if not q:
        return
    items = _load(LEARNING_QUEUE_FILE, [])
    items.append({"question": q, "source": source, "timestamp": time.time()})
    items = items[-2000:]
    _save(LEARNING_QUEUE_FILE, items)


def top_gap_questions(days: int = 1, limit: int = 10) -> list[dict]:
    items = _load(LEARNING_QUEUE_FILE, [])
    cutoff = time.time() - days * 86400
    counts: dict[str, int] = {}
    for it in items:
        if float(it.get("timestamp", 0)) < cutoff:
            continue
        q = _normalize_question(it.get("question", ""))
        if not q:
            continue
        counts[q] = counts.get(q, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"question": q, "count": c} for q, c in ranked]


def should_emit_daily_report(now_ts: float | None = None) -> bool:
    now_ts = now_ts or time.time()
    state = _load(LEARNING_REPORT_STATE_FILE, {"last_report_day": ""})
    day = time.strftime("%Y-%m-%d", time.gmtime(now_ts))
    if state.get("last_report_day") == day:
        return False
    state["last_report_day"] = day
    _save(LEARNING_REPORT_STATE_FILE, state)
    return True
