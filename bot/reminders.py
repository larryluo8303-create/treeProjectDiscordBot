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
        "scheduled_at": scheduled_at.isoformat(),
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

    Also updates their last_posted timestamp in the file.
    """
    reminders = _load()
    due = []
    changed = False

    for rem in reminders:
        if rem.get("cancelled"):
            continue

        scheduled = datetime.fromisoformat(rem["scheduled_at"])
        repeat = rem.get("repeat", "none")
        last_posted = rem.get("last_posted")

        if repeat == "none":
            if last_posted:
                continue
            if now < scheduled:
                continue
        else:
            if now < scheduled:
                continue
            if last_posted:
                last_dt = datetime.fromisoformat(last_posted)
                interval = _REPEAT_INTERVALS.get(repeat, timedelta(days=1))
                if now - last_dt < interval:
                    continue

        due.append(rem)
        rem["last_posted"] = now.isoformat()
        changed = True

    if changed:
        _save(reminders)

    return due
