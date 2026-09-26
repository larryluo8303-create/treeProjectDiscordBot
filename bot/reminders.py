"""Scheduled reminders — market open, data releases, custom alerts.

Uses the same persistence pattern as scheduler.py.
Persisted to ``data/reminders.json``.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from bot.utils import atomic_json_write, data_path
from bot.scheduler import _ensure_aware, _parse_stored_dt

logger = logging.getLogger(__name__)

REMINDERS_FILE = data_path(os.getenv("REMINDERS_FILE", "data/reminders.json"))

_REPEAT_INTERVALS: dict[str, timedelta] = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


def _load() -> list[dict]:
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(data: list[dict]) -> None:
    atomic_json_write(REMINDERS_FILE, data, ensure_ascii=False, indent=2)


def add_reminder(
    title: str,
    message: str,
    scheduled_at: datetime,
    channel_ids: list[int],
    created_by: int,
    repeat: str = "none",
) -> dict:
    """Add a new scheduled reminder."""
    reminders = _load()
    reminder = {
        "id": f"rem_{uuid.uuid4().hex[:8]}",
        "title": title,
        "message": message,
        "scheduled_at": _ensure_aware(scheduled_at).isoformat(),
        "repeat": repeat,
        "channel_ids": channel_ids,
        "last_posted": None,
        "cancelled": False,
        "created_by": created_by,
    }
    reminders.append(reminder)
    _save(reminders)
    logger.info("Scheduled reminder %s at %s (repeat=%s)",
                reminder["id"], reminder["scheduled_at"], repeat)
    return reminder


def list_reminders() -> list[dict]:
    """Return all reminders (excluding cancelled)."""
    return [r for r in _load() if not r.get("cancelled")]


def cancel_reminder(reminder_id: str) -> bool:
    """Cancel a reminder. Returns True if found and cancelled."""
    reminders = _load()
    for r in reminders:
        if r["id"] == reminder_id and not r.get("cancelled"):
            r["cancelled"] = True
            _save(reminders)
            logger.info("Cancelled reminder %s", reminder_id)
            return True
    return False


def get_due_reminders(now: datetime) -> list[dict]:
    """Return reminders that are due to be posted.

    Does NOT mark them as posted — the caller must call
    :func:`mark_reminder_posted` after a successful send.  Previously the
    timestamp was written here, before sending, so a failed send still
    counted as "posted" and the reminder was silently lost forever.
    """
    reminders = _load()
    due = []

    for rem in reminders:
        if rem.get("cancelled"):
            continue

        scheduled = _parse_stored_dt(rem.get("scheduled_at"))
        if scheduled is None:
            continue
        repeat = rem.get("repeat", "none")
        last_posted = _parse_stored_dt(rem.get("last_posted"))

        if repeat == "none":
            if last_posted:
                continue
            if now < scheduled:
                continue
        else:
            if now < scheduled:
                continue
            if last_posted:
                interval = _REPEAT_INTERVALS.get(repeat, timedelta(days=1))
                if now - last_posted < interval:
                    continue

        due.append(rem)

    return due


def mark_reminder_posted(reminder_id: str, now: datetime) -> None:
    """Record a successful reminder post.  Call only after sent > 0."""
    reminders = _load()
    changed = False
    for rem in reminders:
        if rem.get("id") == reminder_id:
            rem["last_posted"] = _ensure_aware(now).isoformat()
            changed = True
            break
    if changed:
        _save(reminders)
