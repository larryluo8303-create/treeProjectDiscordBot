"""Scheduled tasks for BigTreeSignal promotions and lesson pushes.

Persists data to ``data/promos.json`` and ``data/lessons.json``.
A background loop checks every 60 seconds for items due to be posted.
"""

import json
import logging
import os
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import discord
import openai
from discord.ext import commands, tasks

from bot.config import (
    FAQ_PUSH_CHANNELS,
    FAQ_PUSH_ENABLED,
    FAQ_PUSH_HOUR,
    FAQ_PUSH_MINUTE,
    FEATURE_FEEDBACK_LEARNING,
    FEATURE_SLA_MONITORING,
    PROMO_ENABLED,
    SIGNAL_PRODUCT_NAME,
    SIGNAL_PRODUCT_URL,
)
from bot.reliability import evaluate_and_alert, mark_scheduler_tick
from bot.stats import bot_stats
from bot.utils import atomic_json_write, data_path, resolve_channel

logger = logging.getLogger(__name__)

PROMOS_FILE = data_path(os.getenv("PROMOS_FILE", "data/promos.json"))
LESSONS_FILE = data_path(os.getenv("LESSONS_FILE", "data/lessons.json"))
_FAQ_PUSH_STATE_FILE = data_path("data/faq_push_state.json")

_ET = ZoneInfo("America/New_York")


# ── JSON persistence helpers ─────────────────────────────────────────────────

def _load_json(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_json(path: str, data: list[dict]) -> None:
    atomic_json_write(path, data, ensure_ascii=False, indent=2)


# ── Promo CRUD ───────────────────────────────────────────────────────────────

# Repeat interval mapping shared by promos and lessons
_REPEAT_INTERVALS: dict[str, timedelta] = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}

REPEAT_CHOICES = ["none", "hourly", "daily", "weekly", "monthly"]


def _is_repeat_due(now: datetime, scheduled: datetime, last_posted: str | None, repeat: str) -> bool:
    """Check whether a repeating item is due.

    For hourly: simple interval check (now - last_posted >= 1h).
    For daily/weekly/monthly: anchor to the original *hour:minute* in ET
    so that posts always fire at the configured time, not last_posted + N.
    """
    if not last_posted:
        # Never posted before — due as soon as now >= scheduled
        return now >= scheduled

    last_dt = datetime.fromisoformat(last_posted)

    if repeat == "hourly":
        return now - last_dt >= timedelta(hours=1)

    # For daily / weekly / monthly, compare calendar dates in ET
    now_et = now.astimezone(_ET)
    last_et = last_dt.astimezone(_ET)
    sched_et = scheduled.astimezone(_ET)

    # Has the scheduled hour:minute passed today (in ET)?
    if now_et.hour < sched_et.hour:
        return False
    if now_et.hour == sched_et.hour and now_et.minute < sched_et.minute:
        return False

    # Check if enough calendar days have elapsed since last post
    days_elapsed = (now_et.date() - last_et.date()).days
    if repeat == "daily":
        return days_elapsed >= 1
    if repeat == "weekly":
        return days_elapsed >= 7
    if repeat == "monthly":
        return days_elapsed >= 30

    # Unknown repeat — fallback to interval
    interval = _REPEAT_INTERVALS.get(repeat, timedelta(days=1))
    return now - last_dt >= interval


def add_promo(
    title: str,
    description: str,
    scheduled_at: datetime,
    channel_ids: list[int],
    created_by: int,
    url: str = "",
    promo_type: str = "promo",
    repeat: str = "none",
    dm_role_id: int | None = None,
) -> dict:
    """Add a new scheduled promotion and persist to disk."""
    promos = _load_json(PROMOS_FILE)
    promo = {
        "id": f"promo_{uuid.uuid4().hex[:8]}",
        "type": promo_type,
        "title": title,
        "description": description,
        "url": url,
        "scheduled_at": scheduled_at.isoformat(),
        "repeat": repeat,
        "channel_ids": channel_ids,
        "last_posted": None,
        "cancelled": False,
        "created_by": created_by,
    }
    if dm_role_id:
        promo["dm_role_id"] = dm_role_id
    promos.append(promo)
    _save_json(PROMOS_FILE, promos)
    logger.info("Scheduled promo %s at %s (repeat=%s)", promo["id"], promo["scheduled_at"], repeat)
    return promo


def list_promos() -> list[dict]:
    """Return all promotions (pending and posted, excluding cancelled)."""
    promos = _load_json(PROMOS_FILE)
    return [p for p in promos if not p.get("cancelled")]


def cancel_promo(promo_id: str) -> bool:
    """Cancel a pending promotion. Returns True if found and cancelled."""
    promos = _load_json(PROMOS_FILE)
    for p in promos:
        if p["id"] == promo_id and not p.get("posted") and not p.get("cancelled"):
            p["cancelled"] = True
            _save_json(PROMOS_FILE, promos)
            logger.info("Cancelled promo %s", promo_id)
            return True
    return False


# ── Lesson CRUD ──────────────────────────────────────────────────────────────

def add_lesson(
    title: str,
    content: str,
    scheduled_at: datetime,
    channel_ids: list[int],
    created_by: int,
    repeat: str = "none",
) -> dict:
    """Add a new scheduled lesson and persist to disk."""
    lessons = _load_json(LESSONS_FILE)
    lesson = {
        "id": f"lesson_{uuid.uuid4().hex[:8]}",
        "title": title,
        "content": content,
        "scheduled_at": scheduled_at.isoformat(),
        "repeat": repeat,
        "channel_ids": channel_ids,
        "last_posted": None,
        "cancelled": False,
        "created_by": created_by,
    }
    lessons.append(lesson)
    _save_json(LESSONS_FILE, lessons)
    logger.info("Scheduled lesson %s at %s (repeat=%s)",
                lesson["id"], lesson["scheduled_at"], repeat)
    return lesson


def list_lessons() -> list[dict]:
    """Return all lessons (excluding cancelled)."""
    lessons = _load_json(LESSONS_FILE)
    return [ls for ls in lessons if not ls.get("cancelled")]


def cancel_lesson(lesson_id: str) -> bool:
    """Cancel a lesson. Returns True if found and cancelled."""
    lessons = _load_json(LESSONS_FILE)
    for ls in lessons:
        if ls["id"] == lesson_id and not ls.get("cancelled"):
            ls["cancelled"] = True
            _save_json(LESSONS_FILE, lessons)
            logger.info("Cancelled lesson %s", lesson_id)
            return True
    return False


def sync_auto_push_channels() -> None:
    """Refresh channel lists on auto-created daily jobs after .env changes.

    YouTube lessons and promo-monitor jobs snapshot channel IDs at creation
    time. If push channels are added later, existing daily jobs would keep
    posting to the old list until a new video/promo is created.
    """
    from bot.config import (
        PROMO_CHANNEL_IDS,
        PROMO_PUSH_CHANNELS,
        YOUTUBE_LESSON_PUSH_CHANNELS,
    )

    yt_ids = list(YOUTUBE_LESSON_PUSH_CHANNELS or PROMO_CHANNEL_IDS)
    promo_ids = list(PROMO_PUSH_CHANNELS or PROMO_CHANNEL_IDS)

    lessons = _load_json(LESSONS_FILE)
    lesson_changed = False
    for ls in lessons:
        if ls.get("cancelled") or ls.get("source") != "youtube_monitor":
            continue
        if yt_ids and ls.get("channel_ids") != yt_ids:
            logger.info(
                "YouTube lesson %s push channels updated: %s -> %s",
                ls.get("id"), ls.get("channel_ids"), yt_ids,
            )
            ls["channel_ids"] = yt_ids
            lesson_changed = True
    if lesson_changed:
        _save_json(LESSONS_FILE, lessons)

    promos = _load_json(PROMOS_FILE)
    promo_changed = False
    for p in promos:
        if p.get("cancelled") or p.get("source") != "promo_monitor":
            continue
        if promo_ids and p.get("channel_ids") != promo_ids:
            logger.info(
                "Auto-promo %s push channels updated: %s -> %s",
                p.get("id"), p.get("channel_ids"), promo_ids,
            )
            p["channel_ids"] = promo_ids
            promo_changed = True
    if promo_changed:
        _save_json(PROMOS_FILE, promos)


# ── Scheduler Cog ────────────────────────────────────────────────────────────

class SchedulerCog(commands.Cog):
    """Background loop that checks for due promotions and lessons."""

    def __init__(self, bot: commands.Bot, openai_client: openai.AsyncOpenAI | None = None):
        self.bot = bot
        self._openai_client = openai_client
        self._faq_last_pushed_date: str | None = self._load_faq_push_state()

    @staticmethod
    def _load_faq_push_state() -> str | None:
        try:
            with open(_FAQ_PUSH_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("last_pushed_date")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _save_faq_push_state(self) -> None:
        atomic_json_write(_FAQ_PUSH_STATE_FILE, {"last_pushed_date": self._faq_last_pushed_date})

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._check_scheduled.is_running():
            return
        self._check_scheduled.start()

    async def cog_unload(self) -> None:
        self._check_scheduled.cancel()

    @tasks.loop(seconds=60)
    async def _check_scheduled(self) -> None:
        now = datetime.now(timezone.utc)
        mark_scheduler_tick(now.timestamp())
        if PROMO_ENABLED:
            sync_auto_push_channels()
            await self._process_promos(now)
            await self._process_lessons(now)
        await self._process_reminders(now)
        await self._process_faq_push(now)
        await self._process_learning_gap_report(now)
        if FEATURE_SLA_MONITORING:
            await evaluate_and_alert(self.bot, bot_stats)

    # ── Promos ───────────────────────────────────────────────────────────────

    async def _process_promos(self, now: datetime) -> None:
        promos = _load_json(PROMOS_FILE)
        changed = False

        for promo in promos:
            if promo.get("cancelled"):
                continue

            # Auto-expire promos with an expires_at timestamp
            expires_at = promo.get("expires_at")
            if expires_at:
                if now >= datetime.fromisoformat(expires_at):
                    promo["cancelled"] = True
                    changed = True
                    logger.info("Auto-expired promo %s", promo["id"])
                    continue

            scheduled = datetime.fromisoformat(promo["scheduled_at"])
            repeat = promo.get("repeat", "none")
            last_posted = promo.get("last_posted")

            # Determine if this promo is due
            if repeat == "none":
                if promo.get("posted") or last_posted:
                    continue
                if now < scheduled:
                    continue
            else:
                if not _is_repeat_due(now, scheduled, last_posted, repeat):
                    continue

            # Time to post
            embed = self._build_promo_embed(promo)
            mention = "@everyone\n" if promo.get("mention_everyone") else ""
            sent = 0
            for cid in promo.get("channel_ids", []):
                ch = await resolve_channel(self.bot, cid)
                if ch is None or not hasattr(ch, "send"):
                    logger.warning("Promo %s: channel %s not found or not messageable", promo["id"], cid)
                    continue
                try:
                    await ch.send(content=mention or None, embed=embed)
                    sent += 1
                except Exception as exc:
                    logger.warning("Failed to post promo %s to channel %d: %s",
                                   promo["id"], cid, exc)

            if promo.get("dm_role_id"):
                asyncio.create_task(
                    self._dm_scheduled_promo(dict(promo), embed),
                    name=f"promo-dm-{promo.get('id', '')}",
                )

            promo["last_posted"] = now.isoformat()
            if repeat == "none":
                promo["posted"] = True
            changed = True
            logger.info("Posted promo %s to %d channel(s) (repeat=%s)", promo["id"], sent, repeat)

        if changed:
            _save_json(PROMOS_FILE, promos)

    async def _dm_scheduled_promo(self, promo: dict, embed: discord.Embed) -> None:
        """DM allowlisted notify-role members after a scheduled channel post."""
        from bot.role_dm import broadcast_role_dm, is_allowed_notify_role

        dm_role_id = promo.get("dm_role_id")
        promo_id = promo.get("id")
        if not dm_role_id:
            return
        if not is_allowed_notify_role(int(dm_role_id)):
            logger.warning(
                "Skipping promo DM for %s — role %s not allowlisted",
                promo_id, dm_role_id,
            )
            return

        guild = None
        for cid in promo.get("channel_ids", []):
            ch = self.bot.get_channel(cid)
            if ch is not None and getattr(ch, "guild", None) is not None:
                guild = ch.guild
                break
        if guild is None:
            for g in self.bot.guilds:
                if g.get_role(int(dm_role_id)):
                    guild = g
                    break
        if guild is None:
            logger.warning("Promo %s: cannot resolve guild for dm_role_id %s", promo_id, dm_role_id)
            return
        role = guild.get_role(int(dm_role_id))
        if role is None:
            logger.warning("Promo %s: role %s not found in guild %s", promo_id, dm_role_id, guild.id)
            return
        result = await broadcast_role_dm(guild, role, embed)
        logger.info("Promo %s DM result: %s", promo_id, result)

    @staticmethod
    def _build_promo_embed(promo: dict) -> discord.Embed:
        promo_type = promo.get("type", "promo")

        if promo_type == "trial_signal":
            embed = discord.Embed(
                title=f"📊 {promo['title']}",
                description=promo["description"],
                color=discord.Color.green(),
            )
            embed.set_footer(text=f"🌳 {SIGNAL_PRODUCT_NAME} — 免费信号回顾")
        else:
            embed = discord.Embed(
                title=f"🌳 {promo['title']}",
                description=promo["description"],
                color=discord.Color.gold(),
            )

        url = promo.get("url") or SIGNAL_PRODUCT_URL
        if url:
            embed.add_field(name="🔗 链接", value=f"[点击查看]({url})", inline=False)
        image_url = promo.get("image_url")
        if image_url:
            embed.set_image(url=image_url)
        return embed

    # ── Lessons ──────────────────────────────────────────────────────────────

    async def _process_lessons(self, now: datetime) -> None:
        lessons = _load_json(LESSONS_FILE)
        changed = False

        for lesson in lessons:
            if lesson.get("cancelled"):
                continue

            scheduled = datetime.fromisoformat(lesson["scheduled_at"])
            repeat = lesson.get("repeat", "none")
            last_posted = lesson.get("last_posted")

            # Determine if this lesson is due
            if repeat == "none":
                if last_posted:
                    continue  # already posted once
                if now < scheduled:
                    continue
            else:
                if not _is_repeat_due(now, scheduled, last_posted, repeat):
                    continue

            # Time to post
            embed = discord.Embed(
                title=f"📚 {SIGNAL_PRODUCT_NAME} 教学 — {lesson['title']}",
                description=lesson["content"],
                color=discord.Color.blue(),
            )
            if SIGNAL_PRODUCT_URL:
                embed.set_footer(text=f"🌳 了解更多: {SIGNAL_PRODUCT_URL}")

            sent = 0
            for cid in lesson.get("channel_ids", []):
                ch = await resolve_channel(self.bot, cid)
                if ch is None or not hasattr(ch, "send"):
                    logger.warning("Lesson %s: channel %s not found or not messageable", lesson["id"], cid)
                    continue
                try:
                    await ch.send(embed=embed)
                    sent += 1
                except Exception as exc:
                    logger.warning("Failed to post lesson %s to channel %d: %s",
                                   lesson["id"], cid, exc)

            lesson["last_posted"] = now.isoformat()
            changed = True
            logger.info("Posted lesson %s to %d channel(s) (repeat=%s)",
                        lesson["id"], sent, repeat)

        if changed:
            _save_json(LESSONS_FILE, lessons)

    # ── Reminders ─────────────────────────────────────────────────────────────

    async def _process_reminders(self, now: datetime) -> None:
        from bot.reminders import get_due_reminders
        due = get_due_reminders(now)
        for rem in due:
            embed = discord.Embed(
                title=f"⏰ {rem['title']}",
                description=rem["message"],
                color=discord.Color.orange(),
            )
            sent = 0
            for cid in rem.get("channel_ids", []):
                ch = await resolve_channel(self.bot, cid)
                if ch is None or not hasattr(ch, "send"):
                    logger.warning("Reminder %s: channel %s not found or not messageable", rem["id"], cid)
                    continue
                try:
                    await ch.send(embed=embed)
                    sent += 1
                except Exception as exc:
                    logger.warning("Failed to post reminder %s to channel %d: %s",
                                   rem["id"], cid, exc)
            logger.info("Posted reminder %s to %d channel(s)", rem["id"], sent)

    # ── FAQ daily push ────────────────────────────────────────────────────

    async def _process_faq_push(self, now: datetime) -> None:
        if not FAQ_PUSH_ENABLED or not FAQ_PUSH_CHANNELS:
            return
        now_et = now.astimezone(_ET)
        today_str = now_et.strftime("%Y-%m-%d")
        if self._faq_last_pushed_date == today_str:
            return
        if now_et.hour < FAQ_PUSH_HOUR:
            return
        if now_et.hour == FAQ_PUSH_HOUR and now_et.minute < FAQ_PUSH_MINUTE:
            return
        from bot.faq import generate_faq, get_cached_faq
        if self._openai_client:
            try:
                logger.info("FAQ push: auto-generating FAQ from recent queries...")
                new_items = await generate_faq(self._openai_client)
                # generate_faq returns cached items when not enough data;
                # compare with cache to log accurately.
                cached = get_cached_faq()
                if new_items and new_items != cached:
                    logger.info("FAQ push: generated %d new FAQ items", len(new_items))
                else:
                    logger.info("FAQ push: using cached FAQ (%d items)", len(new_items or []))
                items = new_items
            except Exception as exc:
                logger.warning("FAQ push: auto-generation failed, using cached: %s", exc)
                items = get_cached_faq()
        else:
            items = get_cached_faq()
        if not items:
            logger.info("FAQ push: no FAQ items available — skipping")
            self._faq_last_pushed_date = today_str
            self._save_faq_push_state()
            return
        embed = discord.Embed(
            title="❓ 常见问题 FAQ",
            color=discord.Color.blue(),
        )
        for i, it in enumerate(items, 1):
            q = it.get("q", "") or "—"
            a = it.get("a", "") or "—"
            embed.add_field(name=f"{i}. {q}", value=a, inline=False)
        embed.set_footer(text=f"📅 {today_str} | 每日自动推送")
        sent = 0
        for cid in FAQ_PUSH_CHANNELS:
            ch = await resolve_channel(self.bot, cid)
            if ch is None or not hasattr(ch, "send"):
                logger.warning("FAQ push: channel %s not found or not messageable", cid)
                continue
            try:
                await ch.send(embed=embed)
                sent += 1
            except Exception as exc:
                logger.warning("FAQ push: failed to post to channel %d: %s", cid, exc)
        self._faq_last_pushed_date = today_str
        self._save_faq_push_state()
        logger.info("FAQ push: posted %d items to %d channel(s)", len(items), sent)

    async def _process_learning_gap_report(self, now: datetime) -> None:
        if not FEATURE_FEEDBACK_LEARNING:
            return
        from bot.feedback_learning import should_emit_daily_report, top_gap_questions
        if not should_emit_daily_report(now.timestamp()):
            return
        top = top_gap_questions(days=1, limit=10)
        if not top:
            return
        lines = [f"{i + 1}. {it['question']} ({it['count']})" for i, it in enumerate(top)]
        text = "📘 每日待补 KB Top10\n" + "\n".join(lines)
        try:
            from bot.config import OWNER_USER_ID
            owner = await self.bot.fetch_user(OWNER_USER_ID)
            if owner:
                await owner.send(text)
        except Exception as exc:
            logger.warning("Failed to send daily gap report: %s", exc)
