"""Earnings flash digest — watches Jin10 flash news for earnings releases of
watched tickers and posts a structured Chinese digest to a dedicated channel.

Wired into NewsFeedCog._fetch_and_post_locked: every fetched flash item is
checked (before the important-only filter) so an earnings flash is never
missed even when it is not starred as important.

Config (bot/config.py, env.txt):
- EARNINGS_ENABLED (default false)
- EARNINGS_CHANNEL_ID (single Discord channel id)
- EARNINGS_TICKERS (comma-separated, e.g. "NVDA,AAPL,MSFT")
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord.ext import commands, tasks

from bot.config import EARNINGS_CHANNEL_ID, EARNINGS_ENABLED, EARNINGS_TICKERS
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

POSTED_FILE = data_path(os.getenv("EARNINGS_POSTED_FILE", "data/earnings_posted.json"))

# ticker -> Chinese name used by Jin10 flashes
_CN_NAMES: dict[str, str] = {
    "NVDA": "英伟达",
    "AAPL": "苹果",
    "MSFT": "微软",
    "AMZN": "亚马逊",
    "GOOGL": "谷歌",
    "META": "Meta",
    "TSLA": "特斯拉",
    "AMD": "AMD",
    "AVGO": "博通",
    "MU": "美光",
    "COIN": "Coinbase",
    "MSTR": "Strategy",
}

# Keywords that mark a flash as an earnings release (not just a mention).
# A flash must contain the company name AND at least one hard keyword —
# soft keywords alone (e.g. "市场关注明日财报") are previews, not releases.
_HARD_EARNINGS_KEYWORDS = (
    "每股收益", "每股亏损", "EPS", "eps", "营收", "净利润", "净亏损", "季度业绩",
)
_SOFT_EARNINGS_KEYWORDS = ("财报", "财季", "指引")

# Extract a quarter hint like 第三财季 / Q3 / 第二季度 for dedup keys
_QUARTER_RES = (
    re.compile(r"第([一二三四1234])财季"),
    re.compile(r"第([一二三四1234])季度"),
    re.compile(r"\bQ([1-4])\b", re.IGNORECASE),
    re.compile(r"(\d{4})年第([一二三四1234])季度"),
)


def _watched() -> dict[str, str]:
    """ticker -> Chinese name for configured tickers."""
    out: dict[str, str] = {}
    for t in EARNINGS_TICKERS:
        t = t.strip().upper()
        if t:
            out[t] = _CN_NAMES.get(t, t)
    return out


def match_earnings_flash(text: str) -> str | None:
    """Return the ticker if text looks like an earnings release flash.

    Matches when the text mentions a watched company (Chinese name or
    ticker) together with at least one earnings keyword.
    """
    if not text:
        return None
    has_hard_kw = any(kw in text for kw in _HARD_EARNINGS_KEYWORDS)
    if not has_hard_kw:
        return None
    for ticker, cn in _watched().items():
        if cn and cn in text:
            return ticker
        # ticker as a standalone token, e.g. "NVDA Q3"
        if re.search(rf"\b{re.escape(ticker)}\b", text, re.IGNORECASE):
            return ticker
    return None


def extract_quarter_hint(text: str) -> str:
    for rx in _QUARTER_RES:
        m = rx.search(text or "")
        if m:
            return m.group(0)
    return ""


def _load_posted() -> dict[str, str]:
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_posted(posted: dict[str, str]) -> None:
    try:
        atomic_json_write(POSTED_FILE, posted)
    except OSError as exc:
        logger.warning("Failed to save earnings posted file: %s", exc)


def already_posted(ticker: str, quarter_hint: str) -> bool:
    key = f"{ticker}:{quarter_hint or 'unknown'}"
    return key in _load_posted()


def mark_posted(ticker: str, quarter_hint: str) -> None:
    posted = _load_posted()
    posted[f"{ticker}:{quarter_hint or 'unknown'}"] = "1"
    _save_posted(posted)


_DIGEST_PROMPT = """你是一名财经快讯编辑。根据下面这条财报快讯原文，生成一条中文财报速读，严格按以下格式输出，不要多加别的内容：

**{{ticker}} {{quarter}} 财报速读** 📊
EPS ${{eps}}（预期 ${{eps_est}}，{{eps_verdict}}）
营收 ${{rev}}（预期 ${{rev_est}}，{{rev_verdict}}）
指引：{{guidance}}
点评：{{comment}}

规则：
- {{eps_verdict}} 填"超预期 x%"或"不及预期 x%"或"符合预期"；算不出百分比就只写"超预期"/"不及预期"/"符合预期"
- 原文没有披露的项写"未披露"
- {{guidance}} 用一句话概括公司给出的下季度/全年指引，没有就写"未披露"
- {{comment}} 一句话中性点评，只讲事实（比如哪块业务超预期），绝不给买卖建议、不预测股价
- 数字保留原文单位

快讯原文：
{flash_text}
"""


async def build_digest(ticker: str, flash_text: str, openai_client) -> str | None:
    """Use the LLM to extract numbers from the flash and format the digest."""
    quarter = extract_quarter_hint(flash_text) or "最新"
    prompt = _DIGEST_PROMPT.format(ticker=ticker, quarter=quarter, flash_text=flash_text[:1500])
    # Restore the double-brace placeholders the LLM should fill itself.
    prompt = prompt.replace("{{ticker}}", ticker).replace("{{quarter}}", quarter)
    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text[:1800] if text else None
    except Exception as exc:
        logger.warning("Earnings digest LLM failed for %s: %s", ticker, exc)
        return None


async def maybe_handle_earnings_item(bot, item: dict, openai_client) -> bool:
    """Check one Jin10 flash item; post an earnings digest if it matches.

    Returns True when a digest was posted (or already posted before).
    """
    if not EARNINGS_ENABLED or not EARNINGS_CHANNEL_ID:
        return False
    data = item.get("data") or {}
    raw = data.get("content", "")
    # reuse the same html cleaning as news_feed
    text = re.sub(r"<[^>]+>", "", raw.replace("<br/>", "\n").replace("<br>", "\n")).strip()
    ticker = match_earnings_flash(text)
    if not ticker:
        return False
    quarter = extract_quarter_hint(text)
    if already_posted(ticker, quarter):
        return True
    digest = await build_digest(ticker, text, openai_client)
    if not digest:
        return False
    channel = bot.get_channel(EARNINGS_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(EARNINGS_CHANNEL_ID)
        except (discord.NotFound, discord.Forbidden) as exc:
            logger.warning("Earnings: cannot access channel %d (%s)", EARNINGS_CHANNEL_ID, exc)
            return False
    try:
        await channel.send(digest, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Earnings: failed to post digest for %s: %s", ticker, exc)
        return False
    mark_posted(ticker, quarter)
    logger.info("Earnings: posted digest for %s (%s)", ticker, quarter or "unknown quarter")
    return True


# ---------------------------------------------------------------------------
# Earnings calendar reminders — daily scan of Nasdaq earnings calendar for
# watched tickers; posts a T-1 preview and a day-of reminder to the earnings
# channel. (Feature 1 of 3 requested 2026-09-29.)
# ---------------------------------------------------------------------------

CALENDAR_REMINDED_FILE = data_path(os.getenv("EARNINGS_CAL_FILE", "data/earnings_calendar_reminded.json"))
_TORONTO = ZoneInfo("America/Toronto")

_NASDAQ_CAL_URL = "https://api.nasdaq.com/api/calendar/earnings"
_NASDAQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}

_MONTH_TO_Q = {
    "Jan": 1, "Feb": 1, "Mar": 1,
    "Apr": 2, "May": 2, "Jun": 2,
    "Jul": 3, "Aug": 3, "Sep": 3,
    "Oct": 4, "Nov": 4, "Dec": 4,
}


def quarter_label(fiscal_quarter_ending: str) -> str:
    """'Sep/2026' -> '2026年Q3'."""
    try:
        mon, year = (fiscal_quarter_ending or "").split("/")
        q = _MONTH_TO_Q.get(mon.strip()[:3].title(), 0)
        return f"{year.strip()}年Q{q}" if q else fiscal_quarter_ending
    except (ValueError, AttributeError):
        return fiscal_quarter_ending or ""


async def fetch_earnings_calendar(date_str: str) -> list[dict]:
    """Fetch Nasdaq earnings calendar rows for YYYY-MM-DD."""
    params = {"date": date_str}
    try:
        # trust_env=True: honor HTTPS_PROXY in this VM (launcher also patches
        # aiohttp globally, but be explicit so this works standalone too).
        async with aiohttp.ClientSession(headers=_NASDAQ_HEADERS, trust_env=True) as session:
            async with session.get(_NASDAQ_CAL_URL, params=params, timeout=30) as resp:
                if resp.status != 200:
                    logger.warning("Earnings calendar API status %d for %s", resp.status, date_str)
                    return []
                payload = await resp.json(content_type=None)
    except Exception as exc:
        logger.warning("Earnings calendar fetch failed for %s: %s", date_str, exc)
        return []
    return (payload.get("data") or {}).get("rows") or []


def _load_cal_reminded() -> dict:
    try:
        with open(CALENDAR_REMINDED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cal_reminded(reminded: dict) -> None:
    try:
        atomic_json_write(CALENDAR_REMINDED_FILE, reminded)
    except OSError as exc:
        logger.warning("Failed to save earnings calendar reminded file: %s", exc)


def _post_channel(bot):
    channel = bot.get_channel(EARNINGS_CHANNEL_ID)
    return channel


async def _send_calendar_reminder(bot, row: dict, when: str) -> bool:
    """Post a T-1 preview or day-of reminder for one calendar row."""
    symbol = (row.get("symbol") or "").strip().upper()
    watched = _watched()
    if symbol not in watched:
        return False
    date_str = row.get("_cal_date", "")
    key = f"{symbol}:{date_str}:{when}"
    reminded = _load_cal_reminded()
    if key in reminded:
        return False
    cn = watched[symbol]
    q = quarter_label(row.get("fiscalQuarterEnding", ""))
    eps = (row.get("epsForecast") or "未公布").strip()
    n_est = (row.get("noOfEsts") or "").strip()
    est_txt = f"（{n_est} 家机构）" if n_est and n_est != "0" else ""
    t = (row.get("time") or "").strip()
    time_txt = {"time-not-supplied": "未公布", "before market open": "盘前", "after market close": "盘后"}.get(t, t or "未公布")
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        date_txt = f"{d.month}月{d.day}日"
    except ValueError:
        date_txt = date_str
    if when == "T-1":
        msg = (
            f"📅 **财报预告**：{cn} ({symbol}) 将于**明天 {date_txt}**发布 {q} 财报\n"
            f"市场预期 EPS：{eps}{est_txt}\n"
            f"发布时间：{time_txt}"
        )
    else:
        msg = (
            f"⏰ **今日财报**：{cn} ({symbol}) 将于**今天 {date_txt}**发布 {q} 财报\n"
            f"市场预期 EPS：{eps}{est_txt}\n"
            f"发布时间：{time_txt}\n"
            f"财报发布后速读会自动推送到本频道"
        )
    channel = _post_channel(bot)
    if channel is None:
        try:
            channel = await bot.fetch_channel(EARNINGS_CHANNEL_ID)
        except (discord.NotFound, discord.Forbidden) as exc:
            logger.warning("Earnings calendar: cannot access channel %d (%s)", EARNINGS_CHANNEL_ID, exc)
            return False
    try:
        await channel.send(msg, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("Earnings calendar: failed to post reminder for %s: %s", symbol, exc)
        return False
    reminded[key] = "1"
    _save_cal_reminded(reminded)
    logger.info("Earnings calendar: posted %s reminder for %s (%s)", when, symbol, date_str)
    return True


async def check_earnings_calendar(bot) -> int:
    """Check T-1 and T-0 calendar dates; return number of reminders posted."""
    if not EARNINGS_ENABLED or not EARNINGS_CHANNEL_ID:
        return 0
    today = datetime.now(_TORONTO).date()
    posted = 0
    for offset, when in ((1, "T-1"), (0, "T-0")):
        date_str = (today + timedelta(days=offset)).isoformat()
        rows = await fetch_earnings_calendar(date_str)
        for row in rows:
            row["_cal_date"] = date_str
            if await _send_calendar_reminder(bot, row, when):
                posted += 1
    return posted


class EarningsCalendarCog(commands.Cog):
    """Daily earnings-calendar reminders for watched tickers."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not EARNINGS_ENABLED or not EARNINGS_CHANNEL_ID:
            return
        if not self._reminder_loop.is_running():
            self._reminder_loop.start()
            logger.info("Earnings calendar reminders started")

    def cog_unload(self) -> None:
        self._reminder_loop.cancel()

    @tasks.loop(hours=6)
    async def _reminder_loop(self) -> None:
        try:
            posted = await check_earnings_calendar(self.bot)
            if posted:
                logger.info("Earnings calendar: posted %d reminder(s)", posted)
        except Exception as exc:
            logger.warning("Earnings calendar loop failed: %s", exc)

    @_reminder_loop.before_loop
    async def _before_loop(self) -> None:
        await self.bot.wait_until_ready()
