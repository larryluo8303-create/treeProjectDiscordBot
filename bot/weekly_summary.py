"""Weekly Summary — collects owner messages and replies from configured channels
over the past week, summarises key points via GPT, and posts the summary.

Default schedule: Saturday 2 PM ET (UTC-4).

Configurable via env:
- WEEKLY_SUMMARY_ENABLED       (default false)
- WEEKLY_SUMMARY_CHANNELS      (comma-separated channel IDs to scan for owner messages)
- WEEKLY_SUMMARY_DAY           (0=Mon … 5=Sat 6=Sun, default 5)
- WEEKLY_SUMMARY_HOUR          (hour in ET / UTC-4, default 14)
- WEEKLY_SUMMARY_POST_CHANNELS (where to post the summary; falls back to WEEKLY_SUMMARY_CHANNELS)
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
    LLM_MODEL,
    OWNER_USER_ID,
    WEEKLY_SUMMARY_CHANNELS,
    WEEKLY_SUMMARY_DAY,
    WEEKLY_SUMMARY_ENABLED,
    WEEKLY_SUMMARY_HOUR,
    WEEKLY_SUMMARY_MINUTE,
    WEEKLY_SUMMARY_POST_CHANNELS,
)
from bot.utils import save_summary

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


# ── Message collection ─────────────────────────────────────────────────────

async def collect_owner_messages(
    bot: commands.Bot,
    channel_ids: list[int],
    owner_id: int,
    since: datetime,
    limit: int = 5000,
    oldest_first: bool = True,
) -> list[dict]:
    """Fetch owner messages and owner replies from the given channels since ``since``.

    Returns a list of dicts: ``{"channel": str, "time": str, "content": str, "is_reply": bool}``.
    """
    messages: list[dict] = []
    per_channel = max(1, min(5000, limit))

    for cid in channel_ids:
        channel = bot.get_channel(cid)
        if channel is None:
            try:
                channel = await bot.fetch_channel(cid)
            except Exception:
                logger.warning("Summary: cannot access channel %d", cid)
                continue

        if not hasattr(channel, "history"):
            logger.warning("Summary: channel %d has no message history", cid)
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
            logger.warning("Summary: no permission to read channel %d", cid)
        except Exception as exc:
            logger.warning("Summary: error reading channel %d: %s", cid, exc)

    return messages


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
            await self._run_summary()
            await interaction.followup.send("✅ 本周总结已推送。", ephemeral=True)
        except Exception as exc:
            logger.exception("Manual weekly summary failed: %s", exc)
            await interaction.followup.send(f"❌ 推送失败: {exc}", ephemeral=True)

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

    async def _loop(self) -> None:
        """Sleep until the target day+hour, fire summary, repeat."""
        try:
            logger.info("Weekly summary: entering scheduling loop")
            while True:
                try:
                    wait_seconds = self._seconds_until_next()
                    logger.info("Weekly summary: next run in %.0f seconds (%.1f hours)", wait_seconds, wait_seconds / 3600)
                    await asyncio.sleep(wait_seconds)
                    logger.info("Weekly summary: woke up, starting run")
                    await self._run_summary()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("Weekly summary: unexpected error in loop: %s", exc)
                    await asyncio.sleep(60)  # avoid tight retry loop
        except asyncio.CancelledError:
            logger.info("Weekly summary: loop cancelled")

    def _seconds_until_next(self) -> float:
        """Compute seconds until the next occurrence of the target day+hour in ET."""
        now_et = datetime.now(_ET)
        target_day = max(0, min(6, WEEKLY_SUMMARY_DAY))
        target_hour = max(0, min(23, WEEKLY_SUMMARY_HOUR))

        days_ahead = target_day - now_et.weekday()
        if days_ahead < 0:
            days_ahead += 7

        target_minute = max(0, min(59, WEEKLY_SUMMARY_MINUTE))

        target = now_et.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        target += timedelta(days=days_ahead)

        if target <= now_et:
            target += timedelta(weeks=1)

        return (target - now_et).total_seconds()

    async def _run_summary(self) -> None:
        """Collect, summarise, and post the weekly summary."""
        try:
            now = datetime.now(timezone.utc)
            since = now - timedelta(days=7)

            logger.info("Weekly summary: collecting owner messages since %s", since.isoformat())

            messages = await collect_owner_messages(
                bot=self.bot,
                channel_ids=WEEKLY_SUMMARY_CHANNELS,
                owner_id=OWNER_USER_ID,
                since=since,
            )

            if not messages:
                logger.info("Weekly summary: no owner messages found this week — skipping")
                return

            logger.info("Weekly summary: collected %d owner messages, generating summary", len(messages))

            messages_text = format_messages_for_gpt(messages)
            summary = await generate_summary(self._openai_client, messages_text)

            if not summary:
                logger.warning("Weekly summary: GPT returned empty summary — skipping")
                return

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
            post_channels = WEEKLY_SUMMARY_POST_CHANNELS if WEEKLY_SUMMARY_POST_CHANNELS else list(WEEKLY_SUMMARY_CHANNELS)

            sent = 0
            for cid in post_channels:
                ch = self.bot.get_channel(cid)
                if ch is None:
                    continue
                try:
                    await ch.send(content="@everyone", embed=embed)
                    sent += 1
                except Exception as exc:
                    logger.warning("Weekly summary: failed to post to channel %d: %s", cid, exc)

            logger.info("Weekly summary: posted to %d channel(s)", sent)

            # Persist for API clients
            save_summary(
                summary_type="weekly",
                title=f"📋 本周重点总结 ({week_start} – {week_end})",
                content=summary,
                message_count=len(messages),
                timestamp=now.isoformat(),
            )

        except Exception as exc:
            logger.exception("Weekly summary: error: %s", exc)
