"""Macro event calendar reminders — FOMC decisions, CPI, NFP, PCE.

Posts a T-1 preview and a T-0 morning reminder to the news channel so members
never miss a market-moving data release.

Two sources feed ``events_on``:
1. ``EVENTS`` — hardcoded big-4 dates (FOMC/CPI/NFP/PCE), verified 2026-09-29
   against federalreserve.gov (FOMC), BLS (CPI/NFP) and BEA (PCE) official
   calendars. Update this list if an agency reschedules a release.
2. External weekly economic calendar (ForexFactory JSON feed) — covers all
   other market-moving US releases automatically (ADP, GDP, ISM/PMI, retail
   sales, PPI, JOLTS, ...). Fetched at most every ECON_CAL_TTL seconds and
   cached to disk; the hardcoded list is always used as fallback.

Config (bot/config.py, env.txt):
- MACRO_ENABLED (default false)
- MACRO_CHANNEL_ID (default: first NEWS_CHANNEL_IDS entry)
- ECON_CAL_URL / ECON_CAL_TTL (defaults below; no API key needed)
"""

import asyncio
import json
import logging
import os
import time as _time_mod
import urllib.request
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from bot.config import MACRO_CHANNEL_ID, MACRO_ENABLED, NEWS_CHANNEL_IDS
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

REMIND_FILE = data_path(os.getenv("MACRO_REMIND_FILE", "data/macro_reminded.json"))
_TORONTO = ZoneInfo("America/Toronto")

# (date, short name, detail). Decision/release day, ET.
# FOMC: statement 14:00 ET on the second day of the meeting.
EVENTS: list[tuple[str, str, str]] = [
    # --- 2026 (verified 2026-09-29) ---
    ("2026-10-28", "FOMC 议息决议", "美联储 10 月议息决议 14:00 ET 公布"),
    ("2026-10-29", "PCE 物价指数", "9 月 PCE（美联储最看重的通胀指标）8:30 ET"),
    ("2026-11-06", "非农就业", "10 月非农就业报告 8:30 ET"),
    ("2026-11-10", "CPI", "10 月 CPI 8:30 ET"),
    ("2026-11-25", "PCE 物价指数", "10 月 PCE 8:30 ET"),
    ("2026-12-04", "非农就业", "11 月非农就业报告 8:30 ET"),
    ("2026-12-09", "FOMC 议息决议", "美联储 12 月议息决议 14:00 ET（含点阵图/经济预测）"),
    ("2026-12-10", "CPI", "11 月 CPI 8:30 ET"),
    # --- 2027 ---
    ("2027-01-08", "非农就业", "12 月非农就业报告 8:30 ET"),
    ("2027-01-14", "CPI", "12 月 CPI 8:30 ET"),
    ("2027-01-27", "FOMC 议息决议", "美联储 1 月议息决议 14:00 ET"),
    ("2027-02-05", "非农就业", "1 月非农就业报告 8:30 ET"),
    ("2027-03-05", "非农就业", "2 月非农就业报告 8:30 ET"),
    ("2027-03-17", "FOMC 议息决议", "美联储 3 月议息决议 14:00 ET（含点阵图/经济预测）"),
    ("2027-04-28", "FOMC 议息决议", "美联储 4 月议息决议 14:00 ET"),
    ("2027-06-09", "FOMC 议息决议", "美联储 6 月议息决议 14:00 ET（含点阵图/经济预测）"),
    ("2027-07-28", "FOMC 议息决议", "美联储 7 月议息决议 14:00 ET"),
    ("2027-09-15", "FOMC 议息决议", "美联储 9 月议息决议 14:00 ET（含点阵图/经济预测）"),
    ("2027-10-27", "FOMC 议息决议", "美联储 10 月议息决议 14:00 ET"),
    ("2027-12-08", "FOMC 议息决议", "美联储 12 月议息决议 14:00 ET（含点阵图/经济预测）"),
]

# NOTE (2026-09-29, 已按 BLS/BEA/Fed 官网日历核实):
# - 2026 年没有政府停摆（9 月 2 日已签署短期拨款法案延期至 12 月 11 日），
#   BLS/BEA 发布日历正常。2025 年 10-11 月 43 天停摆导致当年 10 月非农/CPI
#   取消、11 月 CPI 推迟到 12-18 —— 那是 2025 年的事，不要再套用到 2026。
# - PCE 日期来自 BEA 官网 2026 发布日历（9 月 PCE = 10-29，不是 10-30）。


# --- 外部经济日历（方案二：自动覆盖全部重要数据） ---
# 数据源：ForexFactory 本周日历 JSON（公开、无需 API key），覆盖 ADP/GDP/PMI/
# 零售销售/PPI/JOLTS 等全部 High/Medium 级别美国数据。拉取失败时自动降级为
# 仅用硬编码 EVENTS 表 + 本地缓存，不影响简报生成。
ECON_CAL_URL = os.getenv(
    "ECON_CAL_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
)
ECON_CAL_CACHE_FILE = data_path(os.getenv("ECON_CAL_CACHE_FILE", "data/econ_calendar_cache.json"))
ECON_CAL_TTL = int(os.getenv("ECON_CAL_TTL", "21600"))  # 6 小时
_CAL_IMPACTS = {"High", "Medium"}  # 只收录重要级别；Low/Holiday 过滤掉

# ForexFactory 英文标题 → 简报中文名；未命中时直接显示英文原标题。
_CAL_TITLE_CN = {
    "ADP Non-Farm Employment Change": "ADP 就业",
    "Non-Farm Employment Change": "非农就业",
    "Unemployment Rate": "失业率",
    "Average Hourly Earnings m/m": "平均时薪",
    "CPI m/m": "CPI",
    "Core CPI m/m": "核心 CPI",
    "CPI y/y": "CPI（同比）",
    "Core CPI y/y": "核心 CPI（同比）",
    "PPI m/m": "PPI",
    "Core PPI m/m": "核心 PPI",
    "PPI y/y": "PPI（同比）",
    "Core PCE Price Index m/m": "核心 PCE 物价指数",
    "PCE Price Index m/m": "PCE 物价指数",
    "Personal Income m/m": "个人收入",
    "Personal Spending m/m": "个人支出",
    "Advance GDP q/q": "GDP（初值）",
    "Prelim GDP q/q": "GDP（修正值）",
    "Final GDP q/q": "GDP（终值）",
    "Advance GDP Price Index q/q": "GDP 物价指数（初值）",
    "Prelim GDP Price Index q/q": "GDP 物价指数（修正值）",
    "Final GDP Price Index q/q": "GDP 物价指数（终值）",
    "Advance Retail Sales m/m": "零售销售",
    "Retail Sales m/m": "零售销售",
    "Core Retail Sales m/m": "核心零售销售",
    "ISM Manufacturing PMI": "ISM 制造业 PMI",
    "ISM Services PMI": "ISM 服务业 PMI",
    "Chicago PMI": "芝加哥 PMI",
    "JOLTS Job Openings": "JOLTS 职位空缺",
    "Initial Jobless Claims": "初请失业金",
    "Unemployment Claims": "初请失业金",
    "Continuing Jobless Claims": "续请失业金",
    "Durable Goods Orders m/m": "耐用品订单",
    "Core Durable Goods Orders m/m": "核心耐用品订单",
    "Factory Orders m/m": "工厂订单",
    "Trade Balance": "贸易帐",
    "Housing Starts": "新屋开工",
    "Building Permits": "营建许可",
    "New Home Sales": "新屋销售",
    "Existing Home Sales": "成屋销售",
    "Pending Home Sales m/m": "成屋签约销售",
    "Consumer Confidence": "谘商会消费者信心",
    "Prelim UoM Consumer Sentiment": "密大消费者信心（初值）",
    "Revised UoM Consumer Sentiment": "密大消费者信心（修正值）",
    "Construction Spending m/m": "营建支出",
    "Crude Oil Inventories": "EIA 原油库存",
    "FOMC Statement": "FOMC 决议声明",
    "Federal Funds Rate": "联邦基金利率",
    "FOMC Press Conference": "FOMC 新闻发布会",
    "FOMC Meeting Minutes": "FOMC 会议纪要",
    "Employment Cost Index q/q": "就业成本指数",
    "Wholesale Inventories m/m": "批发库存",
}


def _read_calendar_cache() -> list:
    """Read cached calendar events from disk (no network). [] if none."""
    try:
        with open(ECON_CAL_CACHE_FILE, "r", encoding="utf-8") as f:
            blob = json.load(f)
        events = blob.get("events")
        return events if isinstance(events, list) else []
    except (OSError, ValueError):
        return []


def refresh_calendar(force: bool = False) -> list:
    """Refresh the weekly econ-calendar cache if stale.

    Returns the event list (fresh, stale cache, or [] on total failure).
    Safe to call from a thread; never raises.
    """
    cached = _read_calendar_cache()
    fetched_at = 0
    try:
        with open(ECON_CAL_CACHE_FILE, "r", encoding="utf-8") as f:
            fetched_at = json.load(f).get("fetched_at", 0) or 0
    except (OSError, ValueError):
        pass
    if not force and cached and _time_mod.time() - fetched_at < ECON_CAL_TTL:
        return cached
    try:
        req = urllib.request.Request(
            ECON_CAL_URL, headers={"User-Agent": "bigTreeSignalBot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            events = json.load(resp)
        if not isinstance(events, list):
            raise ValueError("unexpected calendar payload")
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        logger.warning("Econ calendar fetch failed, using cache: %s", exc)
        return cached
    try:
        atomic_json_write(
            ECON_CAL_CACHE_FILE,
            {"fetched_at": int(_time_mod.time()), "events": events},
        )
    except OSError as exc:
        logger.warning("Failed to save econ calendar cache: %s", exc)
    logger.info("Econ calendar refreshed: %d events", len(events))
    return events


def _calendar_events_on(date_str: str, events: list) -> list[tuple[str, str, str]]:
    """Filter cached calendar to USD High/Medium data releases on date_str."""
    out: list[tuple[int, str, str]] = []
    for e in events:
        try:
            if not isinstance(e, dict) or e.get("country") != "USD":
                continue
            if e.get("impact") not in _CAL_IMPACTS:
                continue
            title = (e.get("title") or "").strip()
            if not title or "speaks" in title.lower():
                continue  # 纯讲话类不算"数据"，保持列表聚焦
            dt = datetime.fromisoformat(e["date"]).astimezone(_TORONTO)
        except (KeyError, ValueError, TypeError):
            continue
        if dt.date().isoformat() != date_str:
            continue
        name = _CAL_TITLE_CN.get(title, title)
        hm = f"{dt.hour}:{dt.minute:02d}"
        fc = (e.get("forecast") or "").strip()
        pv = (e.get("previous") or "").strip()
        extra = ""
        if fc or pv:
            bits = []
            if fc:
                bits.append(f"预期 {fc}")
            if pv:
                bits.append(f"前值 {pv}")
            extra = f"（{'，'.join(bits)}）"
        out.append((dt.hour * 60 + dt.minute, name, f"{hm} ET{extra}"))
    out.sort(key=lambda r: r[0])
    return [(date_str, name, detail) for _, name, detail in out]


def _channel_id() -> int:
    if MACRO_CHANNEL_ID:
        return MACRO_CHANNEL_ID
    return NEWS_CHANNEL_IDS[0] if NEWS_CHANNEL_IDS else 0


def events_on(date_str: str) -> list[tuple[str, str, str]]:
    """All macro events on date_str: hardcoded big-4 + external calendar.

    Calendar part reads from the local cache only (no network here); call
    ``refresh_calendar`` beforehand (e.g. via ``asyncio.to_thread``) to make
    sure the cache is fresh.
    """
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for e in EVENTS:
        if e[0] == date_str and e[1] not in seen:
            out.append(e)
            seen.add(e[1])
    for e in _calendar_events_on(date_str, _read_calendar_cache()):
        if e[1] not in seen:
            out.append(e)
            seen.add(e[1])
    return out


def _load_reminded() -> dict:
    try:
        with open(REMIND_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}
    cutoff = (datetime.now(_TORONTO).date() - timedelta(days=7)).isoformat()
    pruned = {k: v for k, v in data.items() if k[:10] >= cutoff}
    if len(pruned) != len(data):
        _save_reminded(pruned)
    return pruned


def _save_reminded(reminded: dict) -> None:
    try:
        atomic_json_write(REMIND_FILE, reminded)
    except OSError as exc:
        logger.warning("Failed to save macro reminded file: %s", exc)


async def _post(bot, text: str) -> bool:
    channel_id = _channel_id()
    if not channel_id:
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
        logger.warning("Macro: failed to post: %s", exc)
        return False
    return True


async def check_macro_calendar(bot) -> int:
    """Post T-1 previews and T-0 reminders for macro events. Returns count."""
    if not MACRO_ENABLED:
        return 0
    await asyncio.to_thread(refresh_calendar)  # 外部日历先刷新（失败则用缓存/硬编码表）
    today = datetime.now(_TORONTO).date()
    reminded = _load_reminded()
    posted = 0
    for offset, when in ((1, "T-1"), (0, "T-0")):
        date_str = (today + timedelta(days=offset)).isoformat()
        for _, name, detail in events_on(date_str):
            key = f"{date_str}:{name}:{when}"
            if key in reminded:
                continue
            d = datetime.strptime(date_str, "%Y-%m-%d")
            date_txt = f"{d.month}月{d.day}日"
            if when == "T-1":
                msg = f"📊 **宏观前瞻**：**{name}**将于**明天 {date_txt}**公布\n{detail}"
            else:
                msg = (
                    f"⏰ **今日宏观**：**{name}**将于**今天 {date_txt}**公布\n"
                    f"{detail}\n数据公布前后市场波动可能加大，仅为日历提醒，不构成投资建议。"
                )
            if await _post(bot, msg):
                reminded[key] = "1"
                _save_reminded(reminded)
                posted += 1
                logger.info("Macro: posted %s reminder for %s (%s)", when, name, date_str)
    return posted


class MacroCog(commands.Cog):
    """Daily macro-event calendar reminders."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not MACRO_ENABLED:
            return
        if not self._macro_loop.is_running():
            self._macro_loop.start()
            logger.info("Macro calendar reminders started")

    def cog_unload(self) -> None:
        self._macro_loop.cancel()

    @tasks.loop(time=time(hour=8, minute=0, tzinfo=_TORONTO))
    async def _macro_loop(self) -> None:
        try:
            await check_macro_calendar(self.bot)
        except Exception as exc:
            logger.warning("Macro loop failed: %s", exc)

    @_macro_loop.before_loop
    async def _before_loop(self) -> None:
        await self.bot.wait_until_ready()
