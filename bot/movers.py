"""Unusual stock movement alerts — polls Yahoo Finance quotes for watched
tickers during US market hours and posts an alert when intraday move vs
previous close crosses thresholds (3% then 5%).

Each alert tries to attach a possible reason from recent Jin10 flashes
mentioning the company.

Config (bot/config.py, env.txt):
- MOVERS_ENABLED (default false)
- MOVERS_CHANNEL_ID (default: first NEWS_CHANNEL_IDS entry)
- MOVERS_THRESHOLD_PCT (default 3.0)
- MOVERS_ESCALATE_PCT (default 5.0)
- MOVERS_POLL_MINUTES (default 15)
"""

import json
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord.ext import commands, tasks

from bot.config import (
    MOVERS_CHANNEL_ID,
    MOVERS_ENABLED,
    MOVERS_ESCALATE_PCT,
    MOVERS_POLL_MINUTES,
    MOVERS_THRESHOLD_PCT,
    NEWS_CHANNEL_IDS,
)
from bot.earnings import _watched
from bot.news_feed import JIN10_API_URL, JIN10_HEADERS, JIN10_PARAMS, _clean_html, _extract_items
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

ALERTED_FILE = data_path(os.getenv("MOVERS_ALERTED_FILE", "data/movers_alerted.json"))
_TORONTO = ZoneInfo("America/Toronto")

_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _channel_id() -> int:
    if MOVERS_CHANNEL_ID:
        return MOVERS_CHANNEL_ID
    return NEWS_CHANNEL_IDS[0] if NEWS_CHANNEL_IDS else 0


def _market_open_now() -> bool:
    now = datetime.now(_TORONTO)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def _load_alerted() -> dict:
    try:
        with open(ALERTED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}
    # Prune keys older than 7 days so the file doesn't grow forever.
    # Keys look like "2026-09-29:NVDA:3".
    cutoff = (datetime.now(_TORONTO).date() - timedelta(days=7)).isoformat()
    pruned = {k: v for k, v in data.items() if k[:10] >= cutoff}
    if len(pruned) != len(data):
        _save_alerted(pruned)
    return pruned


def _save_alerted(alerted: dict) -> None:
    try:
        atomic_json_write(ALERTED_FILE, alerted)
    except OSError as exc:
        logger.warning("Failed to save movers alerted file: %s", exc)


async def fetch_quote(session: aiohttp.ClientSession, ticker: str) -> tuple[float | None, float | None, int | None]:
    """Return (regular price, previous close, regularMarketTime epoch) via Yahoo v8 chart."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
    try:
        async with session.get(url, headers=_YAHOO_HEADERS, timeout=20) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json(content_type=None)
    except Exception as exc:
        logger.warning("Movers: quote fetch failed for %s: %s", ticker, exc)
        return None, None, None
    try:
        meta = payload["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose")
        ts = meta.get("regularMarketTime")
        if price is None or prev is None or prev == 0:
            return None, None, None
        return float(price), float(prev), int(ts) if ts else None
    except (KeyError, IndexError, TypeError, ValueError):
        return None, None, None


def _quote_is_today(market_ts: int | None) -> bool:
    """Guard against market holidays: on a holiday Yahoo returns the last
    session's close as regularMarketPrice, which would look like a stale move
    vs chartPreviousClose. Only trust quotes timestamped today (ET)."""
    if not market_ts:
        return False
    quote_day = datetime.fromtimestamp(market_ts, tz=_TORONTO).date().isoformat()
    return quote_day == datetime.now(_TORONTO).date().isoformat()


async def find_related_flashes(session: aiohttp.ClientSession, cn_name: str, limit: int = 2) -> list[str]:
    """Recent Jin10 flash titles mentioning the company (possible reason)."""
    try:
        async with session.get(JIN10_API_URL, params=JIN10_PARAMS, headers=JIN10_HEADERS, timeout=20) as resp:
            if resp.status != 200:
                return []
            payload = await resp.json(content_type=None)
    except Exception:
        return []
    items = _extract_items(payload)
    out: list[str] = []
    for item in items[:40]:
        data = item.get("data") or {}
        text = _clean_html(data.get("content", ""))
        if cn_name and cn_name in text and len(text) > 10:
            # Use the title part if present
            title = text.split("\n")[0].strip()
            if title and title not in out:
                out.append(title[:120])
        if len(out) >= limit:
            break
    return out


def _level_for(pct: float) -> int | None:
    a = abs(pct)
    if a >= MOVERS_ESCALATE_PCT:
        return 5
    if a >= MOVERS_THRESHOLD_PCT:
        return 3
    return None


async def check_movers(bot) -> int:
    """Poll quotes; post alerts for threshold crossings. Returns alert count."""
    if not MOVERS_ENABLED:
        return 0
    channel_id = _channel_id()
    if not channel_id:
        return 0
    if not _market_open_now():
        return 0
    today = datetime.now(_TORONTO).date().isoformat()
    alerted = _load_alerted()
    watched = _watched()
    posted = 0
    async with aiohttp.ClientSession(trust_env=True) as session:
        for ticker, cn in watched.items():
            price, prev, market_ts = await fetch_quote(session, ticker)
            if price is None:
                continue
            if not _quote_is_today(market_ts):
                # Market holiday (or stale quote): skip to avoid false alerts.
                continue
            pct = (price - prev) / prev * 100
            level = _level_for(pct)
            if level is None:
                continue
            key = f"{today}:{ticker}:{level}"
            if key in alerted:
                continue
            direction = "🔺" if pct > 0 else "🔻"
            reasons = await find_related_flashes(session, cn)
            reason_txt = ""
            if reasons:
                reason_txt = "\n可能相关：\n" + "\n".join(f"• {r}" for r in reasons)
            msg = (
                f"🚨 **个股异动**{direction}：{cn} ({ticker}) 当前 **${price:.2f}**，"
                f"{'涨' if pct > 0 else '跌'} **{abs(pct):.1f}%**（相对昨收 ${prev:.2f}）"
                f"{reason_txt}"
            )
            channel = bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden):
                    continue
            try:
                await channel.send(msg, allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.HTTPException) as exc:
                logger.warning("Movers: failed to post alert for %s: %s", ticker, exc)
                continue
            alerted[key] = "1"
            _save_alerted(alerted)
            posted += 1
            logger.info("Movers: posted %d%% alert for %s (%+.1f%%)", level, ticker, pct)
    return posted


class MoversCog(commands.Cog):
    """Intraday unusual-movement alerts for watched tickers."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not MOVERS_ENABLED:
            return
        if not self._movers_loop.is_running():
            self._movers_loop.change_interval(minutes=MOVERS_POLL_MINUTES)
            self._movers_loop.start()
            logger.info(
                "Movers alerts started (threshold=%.1f%%, escalate=%.1f%%, every %dm)",
                MOVERS_THRESHOLD_PCT, MOVERS_ESCALATE_PCT, MOVERS_POLL_MINUTES,
            )

    def cog_unload(self) -> None:
        self._movers_loop.cancel()

    @tasks.loop(minutes=15)
    async def _movers_loop(self) -> None:
        try:
            await check_movers(self.bot)
        except Exception as exc:
            logger.warning("Movers loop failed: %s", exc)

    @_movers_loop.before_loop
    async def _before_loop(self) -> None:
        await self.bot.wait_until_ready()
