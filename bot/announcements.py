"""Corporate announcement monitor — scans Jin10 flashes for watched tickers.

Catches buybacks, secondary offerings/dilution, and analyst rating changes,
which the earnings digest doesn't cover. Posts a short alert to the news
channel with the flash excerpt as context.

Called from NewsFeedCog alongside the earnings scan (runs on ALL items,
before the important-only filter). No LLM needed — keyword match only.

Config (bot/config.py, env.txt):
- ANNOUNCE_ENABLED (default false)
- ANNOUNCE_CHANNEL_ID (default: first NEWS_CHANNEL_IDS entry)
"""

import json
import logging
import os
import re

import discord

from bot.config import ANNOUNCE_CHANNEL_ID, ANNOUNCE_ENABLED, NEWS_CHANNEL_IDS
from bot.earnings import _CN_NAMES, _watched
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

POSTED_FILE = data_path(os.getenv("ANNOUNCE_POSTED_FILE", "data/announcements_posted.json"))

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _clean_html(text: str) -> str:
    """Strip HTML tags from Jin10 content (local copy to avoid a circular
    import with bot.news_feed)."""
    if not text:
        return ""
    text = _BR_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()

# category -> keywords (matched case-insensitively against flash text)
_CATEGORIES: dict[str, list[str]] = {
    "股票回购": ["回购", "buyback", "buy-back", "股份回购"],
    "增发/融资": ["增发", "配股", "定向增发", "secondary offering", "follow-on", "公开募股", "可转债"],
    "评级变化": ["上调评级", "下调评级", "上调目标价", "下调目标价", "目标价", "评级", "重申",
             "upgrade", "downgrade", "price target", "initiated coverage", "首予"],
}

# If it looks like an earnings release, the earnings digest owns it — skip here.
_EARNINGS_HINTS = ["每股收益", "eps", "营收", "净利润"]


def _channel_id() -> int:
    if ANNOUNCE_CHANNEL_ID:
        return ANNOUNCE_CHANNEL_ID
    return NEWS_CHANNEL_IDS[0] if NEWS_CHANNEL_IDS else 0


def _load_posted() -> set:
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except (OSError, ValueError):
        return set()


def _save_posted(posted: set) -> None:
    try:
        atomic_json_write(POSTED_FILE, sorted(posted)[-500:])
    except OSError as exc:
        logger.warning("Failed to save announcements posted file: %s", exc)


def match_announcement(text: str) -> tuple[str, str, str] | None:
    """Return (ticker, cn_name, category) if text is a corporate announcement
    for a watched ticker, else None.

    Ticker symbols match as standalone tokens (word boundaries), the same
    rule as bot.earnings.match_earnings_flash — a bare substring would make
    "MU" hit "musk" and "COIN" hit "bitcoin".
    """
    watched = _watched()
    hit_ticker = None
    for ticker, cn in watched.items():
        if cn and cn in text:
            hit_ticker = ticker
            break
        if re.search(rf"\b{re.escape(ticker)}\b", text, re.IGNORECASE):
            hit_ticker = ticker
            break
    if not hit_ticker:
        return None
    # Earnings releases go through the earnings digest instead.
    low = text.lower()
    if any(h in text for h in _EARNINGS_HINTS if h != "eps"):
        return None
    if re.search(r"\beps\b", low):
        return None
    for category, keywords in _CATEGORIES.items():
        # 逆回购 = central-bank reverse repo ops, not a share buyback.
        if category == "股票回购" and "逆回购" in text:
            continue
        if any(k.lower() in low for k in keywords):
            return hit_ticker, watched[hit_ticker], category
    return None


async def maybe_handle_announcement_item(bot, item: dict) -> bool:
    """Post an alert if the flash item is a corporate announcement. Returns True if posted."""
    if not ANNOUNCE_ENABLED:
        return False
    flash_id = str(item.get("id", ""))
    if not flash_id:
        return False
    posted = _load_posted()
    if flash_id in posted:
        return False
    data = item.get("data") or {}
    text = _clean_html(data.get("content", ""))
    if len(text) < 10:
        return False
    matched = match_announcement(text)
    if not matched:
        return False
    ticker, cn, category = matched
    channel_id = _channel_id()
    if not channel_id:
        return False
    excerpt = text.split("\n")[0].strip()[:160]
    msg = (
        f"📢 **公司公告**：{cn} ({ticker})\n"
        f"类型：{category}\n"
        f"内容：{excerpt}"
    )
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden):
            return False
    try:
        await channel.send(msg, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Announcements: failed to post for %s: %s", ticker, exc)
        return False
    posted.add(flash_id)
    _save_posted(posted)
    logger.info("Announcements: posted %s alert for %s", category, ticker)
    return True
