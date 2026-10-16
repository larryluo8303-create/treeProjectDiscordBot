"""Pre-market briefing — posted every trading day at 08:35 ET.

Contents:
- US index futures (ES=F, NQ=F) and VIX
- Today's macro events (from bot.macro)
- Today's earnings for watched tickers (from bot.earnings calendar)
- Pre-market movers among watched tickers (|move| >= threshold vs prev close)

On US market holidays posts a one-line "market closed" note instead.

Config (bot/config.py, env.txt):
- PREMARKET_ENABLED (default false)
- PREMARKET_CHANNEL_ID (default: first NEWS_CHANNEL_IDS entry)
- PREMARKET_THRESHOLD_PCT (default 2.0)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord.ext import commands, tasks

from bot.config import (
    NEWS_CHANNEL_IDS,
    PREMARKET_CHANNEL_ID,
    PREMARKET_ENABLED,
    PREMARKET_THRESHOLD_PCT,
)
from bot.earnings import _watched, fetch_earnings_calendar
from bot.macro import events_on, refresh_calendar
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

BRIEFED_FILE = data_path(os.getenv("PREMARKET_BRIEFED_FILE", "data/premarket_briefed.json"))
_TORONTO = ZoneInfo("America/Toronto")
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_INDEX_NAMES = {"ES=F": "标普期货", "NQ=F": "纳指期货", "^VIX": "VIX 恐慌指数"}


def _channel_id() -> int:
    if PREMARKET_CHANNEL_ID:
        return PREMARKET_CHANNEL_ID
    return NEWS_CHANNEL_IDS[0] if NEWS_CHANNEL_IDS else 0


def _today_str() -> str:
    return datetime.now(_TORONTO).date().isoformat()


def _load_briefed() -> dict:
    try:
        with open(BRIEFED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_briefed(briefed: dict) -> None:
    try:
        atomic_json_write(BRIEFED_FILE, briefed)
    except OSError as exc:
        logger.warning("Failed to save premarket briefed file: %s", exc)


def _ts_is_today(ts: int | None) -> bool:
    if not ts:
        return False
    return datetime.fromtimestamp(ts, tz=_TORONTO).date().isoformat() == _today_str()


async def _fetch_meta(session: aiohttp.ClientSession, symbol: str) -> dict | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    try:
        async with session.get(url, headers=_YAHOO_HEADERS, timeout=20) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json(content_type=None)
            return payload["chart"]["result"][0]["meta"]
    except Exception:
        return None


async def _premarket_price(session: aiohttp.ClientSession, ticker: str) -> tuple[float | None, float | None]:
    """Return (pre-market price, previous close) using 5m bars with prepost."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        "?interval=5m&range=1d&includePrePost=true"
    )
    try:
        async with session.get(url, headers=_YAHOO_HEADERS, timeout=20) as resp:
            if resp.status != 200:
                return None, None
            payload = await resp.json(content_type=None)
            result = payload["chart"]["result"][0]
            meta = result["meta"]
            closes = result["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c]
            prev = meta.get("chartPreviousClose")
            if not closes or prev is None or prev == 0:
                return None, None
            return float(closes[-1]), float(prev)
    except Exception:
        return None, None


async def build_briefing(bot) -> str | None:
    """Compose the pre-market briefing text. Returns None on weekends."""
    now = datetime.now(_TORONTO)
    if now.weekday() >= 5:
        return None
    today = _today_str()
    async with aiohttp.ClientSession(trust_env=True) as session:
        # Index futures + VIX first: their freshness tells us if it's a holiday.
        index_lines = []
        market_closed = False
        for sym in ("ES=F", "NQ=F", "^VIX"):
            meta = await _fetch_meta(session, sym)
            if not meta:
                continue
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose")
            if price is None or prev is None or prev == 0:
                continue
            ts = meta.get("regularMarketTime")
            if sym == "ES=F" and ts and not _ts_is_today(ts):
                market_closed = True
            pct = (price - prev) / prev * 100
            arrow = "🔺" if pct > 0 else "🔻" if pct < 0 else "➖"
            index_lines.append(
                f"{_INDEX_NAMES[sym]}：{price:,.2f} {arrow} {pct:+.2f}%"
            )

        if market_closed:
            return "🏖️ **盘前简报**：今日为美股休市日，无盘前交易。祝假期愉快！"

        lines = [f"☀️ **盘前简报**（{_today_str()[5:].replace('-', '月')}日）", ""]
        lines.append("**股指期货 / 恐慌指数**")
        lines.extend(f"• {l}" for l in index_lines)
        lines.append("")

        # Macro events today (external econ calendar + hardcoded big events)
        await asyncio.to_thread(refresh_calendar)
        macro = events_on(today)
        lines.append("**今日宏观**")
        if macro:
            for _, name, detail in macro:
                lines.append(f"• {name}：{detail}")
        else:
            lines.append("• 无重要宏观数据/事件")
        lines.append("")

        # Earnings today
        watched = _watched()
        rows = await fetch_earnings_calendar(today)
        earn_today = []
        for row in rows:
            sym = (row.get("symbol") or "").strip().upper()
            if sym in watched:
                t = (row.get("time") or "").strip()
                when = {"before market open": "盘前", "after market close": "盘后"}.get(t, "")
                earn_today.append(f"• {watched[sym]} ({sym}) {when}".rstrip())
        lines.append("**今晚财报**")
        lines.extend(earn_today if earn_today else ["• 无关注公司今日发财报"])
        lines.append("")

        # Pre-market movers
        movers = []
        for ticker, cn in watched.items():
            price, prev = await _premarket_price(session, ticker)
            if price is None:
                continue
            pct = (price - prev) / prev * 100
            if abs(pct) >= PREMARKET_THRESHOLD_PCT:
                arrow = "🔺" if pct > 0 else "🔻"
                movers.append(f"• {arrow} {cn} ({ticker}) 盘前 **{pct:+.1f}%** @ ${price:.2f}")
        lines.append(f"**盘前异动**（≥{PREMARKET_THRESHOLD_PCT:.0f}%）")
        lines.extend(movers if movers else ["• 关注公司盘前均无明显异动"])
        lines.append("")
        lines.append("以上为盘前数据汇总，仅供参考，不构成投资建议。")
        return "\n".join(lines)


async def post_briefing(bot) -> bool:
    """Post today's briefing once. Returns True if posted."""
    if not PREMARKET_ENABLED:
        return False
    channel_id = _channel_id()
    if not channel_id:
        return False
    today = _today_str()
    briefed = _load_briefed()
    if today in briefed:
        return False
    text = await build_briefing(bot)
    if text is None:  # weekend
        return False
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden):
            return False
    try:
        await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Premarket: failed to post briefing: %s", exc)
        return False
    briefed[today] = "1"
    _save_briefed(briefed)
    logger.info("Premarket: posted briefing for %s", today)
    return True


class PremarketCog(commands.Cog):
    """Daily 08:35 ET pre-market briefing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not PREMARKET_ENABLED:
            return
        if not self._briefing_loop.is_running():
            self._briefing_loop.start()
            logger.info("Pre-market briefing started (08:35 ET daily)")

    def cog_unload(self) -> None:
        self._briefing_loop.cancel()

    @tasks.loop(time=time(hour=8, minute=35, tzinfo=_TORONTO))
    async def _briefing_loop(self) -> None:
        try:
            await post_briefing(self.bot)
        except Exception as exc:
            logger.warning("Premarket loop failed: %s", exc)

    @_briefing_loop.before_loop
    async def _before_loop(self) -> None:
        await self.bot.wait_until_ready()
