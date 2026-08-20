"""Shared utility functions used across the bot."""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Project root directory — derived from __file__ so it is stable regardless of cwd.
# bot/utils.py -> bot/ -> project_root/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_path(relative: str) -> str:
    """Resolve a data-relative path to an absolute path under PROJECT_ROOT."""
    return os.path.join(PROJECT_ROOT, relative)


def atomic_json_write(path: str, data: Any, **kwargs: Any) -> None:
    """Write *data* as JSON to *path* atomically via a temp file + os.replace.

    Extra keyword arguments are forwarded to ``json.dump`` (e.g.
    ``ensure_ascii=False``, ``indent=2``).
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, **kwargs)
    os.replace(tmp, path)


# ── Summary history persistence ───────────────────────────────────────────

SUMMARIES_FILE = data_path(os.getenv("SUMMARIES_FILE", "data/summaries.json"))
_MAX_SUMMARIES = 100  # keep last 100 summaries


def _load_summaries() -> list[dict]:
    try:
        with open(SUMMARIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_summary(
    *,
    summary_type: str,
    title: str,
    content: str,
    message_count: int,
    timestamp: str,
) -> None:
    """Append a summary record and persist to disk (newest first, capped)."""
    try:
        summaries = _load_summaries()
        summaries.insert(0, {
            "type": summary_type,
            "title": title,
            "content": content,
            "message_count": message_count,
            "timestamp": timestamp,
        })
        summaries = summaries[:_MAX_SUMMARIES]
        atomic_json_write(SUMMARIES_FILE, summaries, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Failed to persist summary: %s", exc)


async def resolve_channel(bot, channel_id: int):
    """Return a channel from cache, or fetch it. None if inaccessible."""
    import discord

    try:
        cid = int(channel_id)
    except (TypeError, ValueError):
        return None
    ch = bot.get_channel(cid)
    if ch is not None:
        return ch
    try:
        return await bot.fetch_channel(cid)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Channel %s not accessible: %s", cid, exc)
        return None


def load_summaries(limit: int = 50, summary_type: str | None = None) -> list[dict]:
    """Return recent summaries, optionally filtered by type."""
    items = _load_summaries()
    if summary_type:
        items = [s for s in items if s.get("type") == summary_type]
    return items[:limit]
