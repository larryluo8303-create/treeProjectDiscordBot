"""Keyword monitoring & owner DM alerts.

Owner configures keywords via /add_alert and /remove_alert.
When a message in any watched channel contains a keyword, the bot
DMs the owner immediately.

Persisted to ``data/alerts.json``.
"""

import json
import logging
import os

from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

ALERTS_FILE = data_path(os.getenv("ALERTS_FILE", "data/alerts.json"))


def _load_keywords() -> list[str]:
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [k.lower() for k in data if isinstance(k, str)]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_keywords(keywords: list[str]) -> None:
    atomic_json_write(ALERTS_FILE, keywords, ensure_ascii=False, indent=2)


# In-memory cache refreshed on add/remove
_cache: list[str] | None = None


def get_keywords() -> list[str]:
    """Return all alert keywords (lowercase)."""
    global _cache
    if _cache is None:
        _cache = _load_keywords()
    return list(_cache)


def add_keyword(keyword: str) -> bool:
    """Add a keyword. Returns True if added (False if duplicate)."""
    global _cache
    kw = keyword.strip().lower()
    if not kw:
        return False
    keywords = _load_keywords()
    if kw in keywords:
        return False
    keywords.append(kw)
    _save_keywords(keywords)
    _cache = keywords
    logger.info("Alert keyword added: %s", kw)
    return True


def remove_keyword(keyword: str) -> bool:
    """Remove a keyword. Returns True if removed."""
    global _cache
    kw = keyword.strip().lower()
    keywords = _load_keywords()
    if kw not in keywords:
        return False
    keywords.remove(kw)
    _save_keywords(keywords)
    _cache = keywords
    logger.info("Alert keyword removed: %s", kw)
    return True


def check_message(text: str) -> list[str]:
    """Return list of alert keywords found in *text*."""
    if not text:
        return []
    lower_text = text.lower()
    return [kw for kw in get_keywords() if kw in lower_text]
