"""Daily Summary — GPT-powered daily summary of owner messages (Mon–Fri).

Posts an automated summary of the channel owner's messages from today
at a configurable time each day.  Completely independent of the weekly
summary feature.

Environment variables (see config.py):
- DAILY_SUMMARY_ENABLED
- DAILY_SUMMARY_CHANNELS        (which channels to scan for owner messages)
- DAILY_SUMMARY_DAYS             (which weekdays to run, default Mon–Fri)
- DAILY_SUMMARY_HOUR             (hour in ET, default 16)
- DAILY_SUMMARY_MINUTE           (minute, default 0)
- DAILY_SUMMARY_POST_CHANNELS    (where to post; falls back to DAILY_SUMMARY_CHANNELS)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import discord
import openai
from discord import app_commands
from discord.ext import commands

from bot.config import (
    DAILY_SUMMARY_CHANNELS,
    DAILY_SUMMARY_DAYS,
    DAILY_SUMMARY_ENABLED,
    DAILY_SUMMARY_HOUR,
    DAILY_SUMMARY_MINUTE,
    DAILY_SUMMARY_POST_CHANNELS,
    LLM_MODEL,
    OWNER_USER_ID,
)
from bot.utils import save_summary
from bot.weekly_summary import collect_owner_messages, format_messages_for_gpt

logger = logging.getLogger(__name__)

# Eastern Time (DST-aware)
_ET = ZoneInfo("America/Toronto")

_DAILY_SYSTEM_PROMPT = (
    "你是一个专业的内容总结助手。用户会给你频道主今天在 Discord 群里发的消息和回复。\n"
    "请用简体中文总结今天的重点内容，包括：\n"
    "1. 频道主分享的主要观点、市场分析或交易策略\n"
    "2. 频道主对群成员问题的关键回复和建议\n"
    "3. 今天重要的市场动态或事件提及\n\n"
    "要求：\n"
    "- 使用清晰的分类标题和要点列表\n"
    "- 保留关键数据和具体建议\n"
    "- 总结应简洁但全面，让没看过原始消息的人也能掌握今天的精华\n"
    "- 用 Discord Markdown 格式排版（**粗体**、- 列表等）\n"
    "- 总结不要超过 3500 个字符（这很重要，因为 Discord 有长度限制）"
)


async def generate_daily_summary(
    openai_client: openai.AsyncOpenAI,
    messages_text: str,
) -> str:
    """Call GPT to summarise the owner's daily messages."""
    try:
        response = await openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _DAILY_SYSTEM_PROMPT},
                {"role": "user", "content": f"以下是频道主今天的所有消息和回复，请总结重点：\n\n{messages_text}"},
            ],
            max_tokens=2000,
            temperature=0.4,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.exception("Daily summary: GPT error: %s", exc)
        return ""


class DailySummaryCog(commands.Cog):
    """Posts a GPT-generated daily summary of owner messages on weekdays."""

    def __init__(self, bot: commands.Bot, openai_client: openai.AsyncOpenAI) -> None:
        self.bot = bot
        self._openai_client = openai_client
        self._task: asyncio.Task | None = None
        self._started: bool = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._started:
            return
        if not DAILY_SUMMARY_ENABLED:
            return
        if not DAILY_SUMMARY_CHANNELS:
            logger.warning("Daily summary enabled but DAILY_SUMMARY_CHANNELS is empty — skipping")
            return
        self._started = True
        self._task = asyncio.create_task(self._loop(), name="daily-summary-loop")
        self._task.add_done_callback(self._task_done)
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days_str = ",".join(day_names[d] for d in sorted(DAILY_SUMMARY_DAYS) if 0 <= d <= 6)
        logger.info(
            "Daily summary started (days=%s, %02d:%02d ET, channels=%s)",
            days_str, DAILY_SUMMARY_HOUR, DAILY_SUMMARY_MINUTE, DAILY_SUMMARY_CHANNELS,
        )

    # ── /daily_summary manual trigger ────────────────────────────────────

    @app_commands.command(name="daily_summary", description="[Owner] 立即生成并推送今日总结")
    async def daily_summary_cmd(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != OWNER_USER_ID:
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self._run_summary()
            await interaction.followup.send("✅ 今日总结已推送。", ephemeral=True)
        except Exception as exc:
            logger.exception("Manual daily summary failed: %s", exc)
            await interaction.followup.send(f"❌ 推送失败: {exc}", ephemeral=True)

    @staticmethod
    def _task_done(task: asyncio.Task) -> None:
        """Log if the background task exits unexpectedly."""
        if task.cancelled():
            logger.info("Daily summary: background task was cancelled")
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Daily summary: background task died with exception: %s", exc, exc_info=exc)

    async def cog_unload(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def _seconds_until_next(self) -> float:
        """Compute seconds until the next scheduled daily summary in ET."""
        now_et = datetime.now(_ET)
        target_hour = max(0, min(23, DAILY_SUMMARY_HOUR))
        target_minute = max(0, min(59, DAILY_SUMMARY_MINUTE))
        allowed_days = set(DAILY_SUMMARY_DAYS) if DAILY_SUMMARY_DAYS else {0, 1, 2, 3, 4}

        # Try today first, then the next 7 days
        for offset in range(8):
            candidate = now_et + timedelta(days=offset)
            if candidate.weekday() not in allowed_days:
                continue
            target = candidate.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if target > now_et:
                return (target - now_et).total_seconds()

        # Fallback: exactly 24 hours (should not happen with 7-day scan)
        return 86400.0

    async def _loop(self) -> None:
        """Sleep until the next scheduled time, fire summary, repeat."""
        try:
            logger.info("Daily summary: entering scheduling loop")
            while True:
                try:
                    wait_seconds = self._seconds_until_next()
                    logger.info("Daily summary: next run in %.0f seconds (%.1f hours)", wait_seconds, wait_seconds / 3600)
                    await asyncio.sleep(wait_seconds)
                    logger.info("Daily summary: woke up, starting run")
                    await self._run_summary()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("Daily summary: unexpected error in loop: %s", exc)
                    await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("Daily summary: loop cancelled")

    async def _run_summary(self) -> None:
        """Collect today's owner messages, summarise, and post."""
        try:
            now = datetime.now(timezone.utc)
            # Collect messages from today only (since midnight ET)
            now_et = datetime.now(_ET)
            midnight_et = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
            since = midnight_et.astimezone(timezone.utc)

            logger.info("Daily summary: collecting owner messages since %s", since.isoformat())

            messages = await collect_owner_messages(
                bot=self.bot,
                channel_ids=DAILY_SUMMARY_CHANNELS,
                owner_id=OWNER_USER_ID,
                since=since,
            )

            if not messages:
                logger.info("Daily summary: no owner messages found today — skipping")
                return

            logger.info("Daily summary: collected %d owner messages, generating summary", len(messages))

            messages_text = format_messages_for_gpt(messages)
            summary = await generate_daily_summary(self._openai_client, messages_text)

            if not summary:
                logger.warning("Daily summary: GPT returned empty summary — skipping")
                return

            # Discord embed description limit is 4096 chars
            if len(summary) > 4000:
                summary = summary[:3997] + "…"

            today_str = now_et.strftime("%Y/%m/%d %A")
            embed = discord.Embed(
                title=f"📋 今日重点总结 ({today_str})",
                description=summary,
                color=discord.Color.blue(),
                timestamp=now,
            )
            embed.set_footer(text=f"基于频道主今日 {len(messages)} 条消息 • AI 自动生成")

            # Determine post channels
            post_channels = DAILY_SUMMARY_POST_CHANNELS if DAILY_SUMMARY_POST_CHANNELS else list(DAILY_SUMMARY_CHANNELS)

            sent = 0
            for cid in post_channels:
                ch = self.bot.get_channel(cid)
                if ch is None:
                    continue
                try:
                    await ch.send(content="@everyone", embed=embed)
                    sent += 1
                except Exception as exc:
                    logger.warning("Daily summary: failed to post to channel %d: %s", cid, exc)

            logger.info("Daily summary: posted to %d channel(s)", sent)

            # Persist for API clients
            save_summary(
                summary_type="daily",
                title=f"📋 今日重点总结 ({today_str})",
                content=summary,
                message_count=len(messages),
                timestamp=now.isoformat(),
            )

        except Exception as exc:
            logger.exception("Daily summary: error: %s", exc)
