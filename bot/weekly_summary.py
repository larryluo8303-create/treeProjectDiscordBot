"""Weekly Summary — collects owner messages and replies from configured channels
over the past week, summarises key points via GPT, and posts the summary.

Default schedule: Saturday 2 PM ET (UTC-4).

Configurable via env:
- WEEKLY_SUMMARY_ENABLED       (default false)
- WEEKLY_SUMMARY_CHANNELS      (comma-separated channel IDs to scan for owner messages)
- WEEKLY_SUMMARY_DAY           (0=Mon … 5=Sat 6=Sun, default 5)
- WEEKLY_SUMMARY_HOUR          (hour in ET / UTC-4, default 14)
- WEEKLY_SUMMARY_MINUTE        (minute of hour, default 0)
- WEEKLY_SUMMARY_POST_CHANNELS (where to post the summary; falls back to WEEKLY_SUMMARY_CHANNELS)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

import discord
import openai
from discord import app_commands
from discord.ext import commands

from bot.config import (
    LLM_MODEL,
    OWNER_USER_ID,
    WEEKLY_SUMMARY_CHANNELS,
    WEEKLY_SUMMARY_DAY,
    WEEKLY_SUMMARY_ENABLED,
    WEEKLY_SUMMARY_HOUR,
    WEEKLY_SUMMARY_MINUTE,
    WEEKLY_SUMMARY_POST_CHANNELS,
)
from bot.utils import load_summaries, save_summary

logger = logging.getLogger(__name__)

# Eastern Time (DST-aware)
_ET = ZoneInfo("America/Toronto")

_SUMMARY_SYSTEM_PROMPT = (
    "你是一个专业的内容总结助手。用户会给你一周内频道主在 Discord 群里发的消息和回复。\n"
    "请用简体中文总结本周重点内容，包括：\n"
    "1. 频道主分享的主要观点、市场分析或交易策略\n"
    "2. 频道主对群成员问题的关键回复和建议\n"
    "3. 本周重要的市场动态或事件提及\n\n"
    "要求：\n"
    "- 使用清晰的分类标题和要点列表\n"
    "- 保留关键数据和具体建议\n"
    "- 总结应简洁但全面，让没看过原始消息的人也能掌握本周精华\n"
    "- 用 Discord Markdown 格式排版（**粗体**、- 列表等）\n"
    "- 总结不要超过 3500 个字符（这很重要，因为 Discord 有长度限制）"
)

_MAX_CONTENT_CHARS = 30000  # Limit total content sent to GPT
_RETRY_SECONDS = 30 * 60  # retry after network / GPT failure
_CATCHUP_GRACE_HOURS = 18  # still run if we wake within this window after target
_SLEEP_CHUNK_SECONDS = 60  # re-check clock often (survives PC sleep better)

RunStatus = Literal["posted", "empty", "failed"]


# ── Message collection ─────────────────────────────────────────────────────

async def collect_owner_messages(
    bot: commands.Bot,
    channel_ids: list[int],
    owner_id: int,
    since: datetime,
    limit: int = 5000,
    oldest_first: bool = True,
) -> tuple[list[dict], list[str]]:
    """Fetch owner messages and owner replies from the given channels since ``since``.

    Returns ``(messages, errors)`` where *errors* lists channel-level failures
    (network / permission). An empty *messages* with non-empty *errors* means
    the run should be retried — not treated as “no messages this week”.
    """
    messages: list[dict] = []
    errors: list[str] = []
    per_channel = max(1, min(5000, limit))

    for cid in channel_ids:
        channel = bot.get_channel(cid)
        if channel is None:
            try:
                channel = await bot.fetch_channel(cid)
            except Exception as exc:
                msg = f"cannot access channel {cid}: {exc}"
                logger.warning("Summary: %s", msg)
                errors.append(msg)
                continue

        if not hasattr(channel, "history"):
            msg = f"channel {cid} has no message history"
            logger.warning("Summary: %s", msg)
            errors.append(msg)
            continue

        channel_name = getattr(channel, "name", str(cid))

        try:
            async for msg in channel.history(
                after=since, limit=per_channel, oldest_first=oldest_first,
            ):
                if msg.author.id != owner_id:
                    continue
                if not msg.content or not msg.content.strip():
                    continue

                is_reply = bool(msg.reference and msg.reference.message_id)
                reply_context = ""

                # Fetch the original message being replied to for context.
                # Use cached resolved_reference first to avoid extra API calls.
                if is_reply:
                    try:
                        ref_msg = msg.reference.resolved
                        if ref_msg is None:
                            ref_msg = await channel.fetch_message(msg.reference.message_id)
                        if ref_msg and ref_msg.content and ref_msg.content.strip():
                            author_name = getattr(ref_msg.author, "display_name", str(ref_msg.author))
                            reply_context = f"[回复 {author_name}: {ref_msg.content.strip()[:200]}]\n"
                    except Exception:
                        pass

                messages.append({
                    "channel": channel_name,
                    "time": msg.created_at.strftime("%m/%d %H:%M"),
                    "content": reply_context + msg.content.strip(),
                    "is_reply": is_reply,
                })
        except discord.Forbidden:
            msg = f"no permission to read channel {cid}"
            logger.warning("Summary: %s", msg)
            errors.append(msg)
        except Exception as exc:
            msg = f"error reading channel {cid}: {exc}"
            logger.warning("Summary: %s", msg)
            errors.append(msg)

    return messages, errors


def format_messages_for_gpt(messages: list[dict]) -> str:
    """Format collected messages into a text block for GPT summarisation."""
    if not messages:
        return ""

    lines: list[str] = []
    total_chars = 0

    for m in messages:
        prefix = m.get("kind") or ("[回复]" if m["is_reply"] else "[发帖]")
        if not prefix.startswith("["):
            prefix = f"[{prefix}]"
        line = f"[{m['time']}] #{m['channel']} {prefix} {m['content']}"
        if total_chars + len(line) > _MAX_CONTENT_CHARS:
            lines.append("... (内容已截断)")
            break
        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines)


# ── GPT summarisation ─────────────────────────────────────────────────────

async def generate_summary(
    openai_client: openai.AsyncOpenAI,
    messages_text: str,
) -> str:
    """Call GPT to summarise the owner's weekly messages."""
    try:
        response = await openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"以下是频道主本周的所有消息和回复，请总结重点：\n\n{messages_text}"},
            ],
            max_tokens=2000,
            temperature=0.4,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.exception("Weekly summary: GPT error: %s", exc)
        return ""


# ── Cog ────────────────────────────────────────────────────────────────────

class WeeklySummaryCog(commands.Cog):
    """Posts a GPT-generated weekly summary of owner messages every Saturday."""

    def __init__(self, bot: commands.Bot, openai_client: openai.AsyncOpenAI) -> None:
        self.bot = bot
        self._openai_client = openai_client
        self._task: asyncio.Task | None = None
        self._started: bool = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._started:
            return
        if not WEEKLY_SUMMARY_ENABLED:
            return
        if not WEEKLY_SUMMARY_CHANNELS:
            logger.warning("Weekly summary enabled but WEEKLY_SUMMARY_CHANNELS is empty — skipping")
            return
        self._started = True
        self._task = asyncio.create_task(self._loop(), name="weekly-summary-loop")
        self._task.add_done_callback(self._task_done)
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_name = day_names[WEEKLY_SUMMARY_DAY] if 0 <= WEEKLY_SUMMARY_DAY <= 6 else f"day{WEEKLY_SUMMARY_DAY}"
        logger.info(
            "Weekly summary started (day=%s, %02d:%02d ET, channels=%s)",
            day_name, WEEKLY_SUMMARY_HOUR, WEEKLY_SUMMARY_MINUTE, WEEKLY_SUMMARY_CHANNELS,
        )

    # ── /weekly_summary manual trigger ─────────────────────────────────

    @app_commands.command(name="weekly_summary", description="[Owner] 立即生成并推送本周总结")
    async def weekly_summary_cmd(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != OWNER_USER_ID:
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            status = await self._run_summary()
            if status == "posted":
                await interaction.followup.send("✅ 本周总结已推送。", ephemeral=True)
            elif status == "empty":
                await interaction.followup.send("⚠️ 本周未找到频道主消息，未推送。", ephemeral=True)
            else:
                await interaction.followup.send(
                    "❌ 推送失败（网络或 GPT 错误），请查看日志后重试。", ephemeral=True,
                )
        except Exception as exc:
            logger.exception("Manual weekly summary failed: %s", exc)
            await interaction.followup.send(f"❌ 推送失败: {type(exc).__name__}", ephemeral=True)

    @staticmethod
    def _task_done(task: asyncio.Task) -> None:
        """Log if the background task exits unexpectedly."""
        if task.cancelled():
            logger.info("Weekly summary: background task was cancelled")
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Weekly summary: background task died with exception: %s", exc, exc_info=exc)

    async def cog_unload(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _sleep_chunked(self, total_seconds: float) -> None:
        """Sleep in short chunks so PC sleep / clock skew is re-checked often."""
        remaining = max(0.0, total_seconds)
        while remaining > 0:
            chunk = min(_SLEEP_CHUNK_SECONDS, remaining)
            await asyncio.sleep(chunk)
            remaining -= chunk
            # If we overslept into (or past) the target window, stop early.
            if self._is_due(grace_hours=_CATCHUP_GRACE_HOURS):
                logger.info("Weekly summary: target window reached during sleep — waking early")
                return

    async def _loop(self) -> None:
        """Sleep until the target day+hour, fire summary, repeat; retry on failure."""
        try:
            logger.info("Weekly summary: entering scheduling loop")
            while True:
                try:
                    if self._is_due(grace_hours=_CATCHUP_GRACE_HOURS):
                        logger.info("Weekly summary: due (catch-up or on schedule) — starting run")
                        status = await self._run_summary()
                        if status == "failed":
                            logger.warning(
                                "Weekly summary: failed — retrying in %d seconds", _RETRY_SECONDS,
                            )
                            await asyncio.sleep(_RETRY_SECONDS)
                            continue
                        # posted / empty → wait for next weekly slot
                        wait_seconds = self._seconds_until_next()
                        logger.info(
                            "Weekly summary: next run in %.0f seconds (%.1f hours)",
                            wait_seconds, wait_seconds / 3600,
                        )
                        await self._sleep_chunked(wait_seconds)
                        continue

                    wait_seconds = self._seconds_until_next()
                    logger.info(
                        "Weekly summary: next run in %.0f seconds (%.1f hours)",
                        wait_seconds, wait_seconds / 3600,
                    )
                    await self._sleep_chunked(wait_seconds)
                    logger.info("Weekly summary: woke up, starting run")
                    status = await self._run_summary()
                    if status == "failed":
                        logger.warning(
                            "Weekly summary: failed — retrying in %d seconds", _RETRY_SECONDS,
                        )
                        await asyncio.sleep(_RETRY_SECONDS)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("Weekly summary: unexpected error in loop: %s", exc)
                    await asyncio.sleep(60)  # avoid tight retry loop
        except asyncio.CancelledError:
            logger.info("Weekly summary: loop cancelled")

    def _target_for_week_containing(self, now_et: datetime) -> datetime:
        """Return this calendar week's scheduled target (may be in the past)."""
        target_day = max(0, min(6, WEEKLY_SUMMARY_DAY))
        target_hour = max(0, min(23, WEEKLY_SUMMARY_HOUR))
        target_minute = max(0, min(59, WEEKLY_SUMMARY_MINUTE))
        days_offset = target_day - now_et.weekday()  # may be negative
        return now_et.replace(
            hour=target_hour, minute=target_minute, second=0, microsecond=0,
        ) + timedelta(days=days_offset)

    def _seconds_until_next(self) -> float:
        """Compute seconds until the next occurrence of the target day+hour in ET."""
        now_et = datetime.now(_ET)
        target = self._target_for_week_containing(now_et)
        if target <= now_et:
            target += timedelta(weeks=1)
        return max(1.0, (target - now_et).total_seconds())

    def _already_posted_since(self, since_et: datetime) -> bool:
        """True if a weekly summary was persisted at/after *since_et*."""
        since_utc = since_et.astimezone(timezone.utc)
        for item in load_summaries(limit=30, summary_type="weekly"):
            ts = item.get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= since_utc:
                return True
        return False

    def _is_due(self, grace_hours: float = _CATCHUP_GRACE_HOURS) -> bool:
        """True if we are within [target, target+grace] and have not posted yet."""
        now_et = datetime.now(_ET)
        target = self._target_for_week_containing(now_et)
        if target > now_et:
            return False
        if now_et > target + timedelta(hours=grace_hours):
            return False
        if self._already_posted_since(target):
            return False
        return True

    async def _run_summary(self) -> RunStatus:
        """Collect, summarise, and post the weekly summary.

        Returns ``posted``, ``empty`` (no owner messages after successful reads),
        or ``failed`` (channel / GPT / post errors — caller should retry).
        """
        try:
            now = datetime.now(timezone.utc)
            since = now - timedelta(days=7)

            logger.info("Weekly summary: collecting owner messages since %s", since.isoformat())

            messages, errors = await collect_owner_messages(
                bot=self.bot,
                channel_ids=WEEKLY_SUMMARY_CHANNELS,
                owner_id=OWNER_USER_ID,
                since=since,
            )

            if errors and not messages:
                logger.warning(
                    "Weekly summary: all channel reads failed (%d error(s)) — will retry",
                    len(errors),
                )
                return "failed"

            if errors:
                logger.warning(
                    "Weekly summary: %d channel(s) failed but got %d message(s) from others",
                    len(errors), len(messages),
                )

            if not messages:
                logger.info("Weekly summary: no owner messages found this week — skipping")
                return "empty"

            logger.info("Weekly summary: collected %d owner messages, generating summary", len(messages))

            messages_text = format_messages_for_gpt(messages)
            summary = await generate_summary(self._openai_client, messages_text)

            if not summary:
                logger.warning("Weekly summary: GPT returned empty summary — will retry")
                return "failed"

            # Build embed
            now_et = datetime.now(_ET)
            week_start = (now_et - timedelta(days=7)).strftime("%m/%d")
            week_end = now_et.strftime("%m/%d")

            # Discord embed description limit is 4096 chars
            if len(summary) > 4000:
                summary = summary[:3997] + "…"

            embed = discord.Embed(
                title=f"📋 本周重点总结 ({week_start} – {week_end})",
                description=summary,
                color=discord.Color.teal(),
                timestamp=now,
            )
            embed.set_footer(text=f"基于频道主本周 {len(messages)} 条消息 • AI 自动生成")

            # Determine post channels
            post_channels = (
                WEEKLY_SUMMARY_POST_CHANNELS
                if WEEKLY_SUMMARY_POST_CHANNELS
                else list(WEEKLY_SUMMARY_CHANNELS)
            )

            from bot.utils import resolve_channel

            sent = 0
            for cid in post_channels:
                ch = await resolve_channel(self.bot, cid)
                if ch is None or not hasattr(ch, "send"):
                    logger.warning("Weekly summary: channel %d not found or not messageable", cid)
                    continue
                try:
                    await ch.send(content="@everyone", embed=embed)
                    sent += 1
                except Exception as exc:
                    logger.warning("Weekly summary: failed to post to channel %d: %s", cid, exc)

            if sent <= 0:
                logger.warning("Weekly summary: failed to post to any channel — will retry")
                return "failed"

            logger.info("Weekly summary: posted to %d channel(s)", sent)

            # Persist for API clients
            save_summary(
                summary_type="weekly",
                title=f"📋 本周重点总结 ({week_start} – {week_end})",
                content=summary,
                message_count=len(messages),
                timestamp=now.isoformat(),
            )
            return "posted"

        except Exception as exc:
            logger.exception("Weekly summary: error: %s", exc)
            return "failed"
