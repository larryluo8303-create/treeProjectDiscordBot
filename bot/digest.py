"""Daily Digest — sends a scheduled channel activity summary to the owner.

Configurable via:
- DIGEST_ENABLED (default false)
- DIGEST_HOUR (0-23, UTC, default 22 = 6pm ET)
- DIGEST_CHANNEL_ID (where to post the digest embed; 0 = DM owner only)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from bot.config import DIGEST_CHANNEL_ID, DIGEST_ENABLED, DIGEST_HOUR, OWNER_USER_ID, TARGET_CHANNEL_IDS
from bot.stats import bot_stats

logger = logging.getLogger(__name__)


class DigestCog(commands.Cog):
    """Sends a daily activity summary at a configured UTC hour."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._digest_task: asyncio.Task | None = None
        self._started: bool = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not DIGEST_ENABLED:
            return
        if self._started:
            return
        if self._digest_task is None or self._digest_task.done():
            self._started = True
            self._digest_task = asyncio.create_task(self._digest_loop())
            logger.info("Daily digest scheduler started (UTC hour=%d)", DIGEST_HOUR)

    async def cog_unload(self) -> None:
        if self._digest_task is not None:
            self._digest_task.cancel()
            self._digest_task = None

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def _digest_loop(self) -> None:
        """Sleep until the target hour, fire digest, repeat."""
        try:
            while True:
                now = datetime.now(timezone.utc)
                target = now.replace(hour=DIGEST_HOUR, minute=0, second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info("Next digest in %.0f seconds (at %s UTC)", wait_seconds, target.isoformat())
                await asyncio.sleep(wait_seconds)
                await self._send_digest()
        except asyncio.CancelledError:
            pass

    # ── Digest builder ────────────────────────────────────────────────────────

    async def _send_digest(self) -> None:
        """Build and send the daily digest."""
        try:
            embed = await self._build_digest_embed()

            # Post to digest channel if configured
            if DIGEST_CHANNEL_ID:
                channel = self.bot.get_channel(DIGEST_CHANNEL_ID)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(DIGEST_CHANNEL_ID)
                    except Exception:
                        channel = None
                if channel:
                    await channel.send(embed=embed)
                    logger.info("Daily digest posted to channel %d", DIGEST_CHANNEL_ID)

            # Also DM the owner
            try:
                owner = await self.bot.fetch_user(OWNER_USER_ID)
                if owner:
                    await owner.send(embed=embed)
                    logger.info("Daily digest DM sent to owner")
            except discord.Forbidden:
                logger.info("Cannot DM owner — DMs disabled")
            except Exception as exc:
                logger.warning("Failed to DM digest to owner: %s", exc)

        except Exception as exc:
            logger.exception("Failed to generate daily digest: %s", exc)

    async def _build_digest_embed(self) -> discord.Embed:
        """Build a rich embed summarizing the last 24h of activity."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        cutoff_ts = cutoff.timestamp()

        # Filter recent queries from the last 24 hours
        recent_24h = [r for r in bot_stats.recent if r.timestamp >= cutoff_ts]

        total = len(recent_24h)
        auto = sum(1 for r in recent_24h if r.action == "auto_reply")
        forwarded = total - auto
        avg_conf = (
            sum(r.confidence for r in recent_24h) / total if total else 0.0
        )
        avg_latency = (
            sum(r.latency_ms for r in recent_24h) / total if total else 0.0
        )

        # Channel breakdown
        channel_counts: dict[int, int] = {}
        for r in recent_24h:
            channel_counts[r.channel_id] = channel_counts.get(r.channel_id, 0) + 1

        # Top questions (up to 5)
        top_qs = recent_24h[-5:] if recent_24h else []
        top_qs.reverse()

        # Unanswered (forwarded) questions
        unanswered = [r for r in recent_24h if r.action != "auto_reply"][-5:]
        unanswered.reverse()

        # Build embed
        embed = discord.Embed(
            title="📊 Daily Digest",
            description=f"Activity summary for the last 24 hours\n{cutoff.strftime('%m/%d %H:%M')} – {now.strftime('%m/%d %H:%M')} UTC",
            color=discord.Color.blue(),
            timestamp=now,
        )

        # Overview
        overview = (
            f"**Total questions:** {total}\n"
            f"**Auto-replied:** {auto}\n"
            f"**Forwarded to owner:** {forwarded}\n"
            f"**Avg confidence:** {avg_conf:.1f}/10\n"
            f"**Avg latency:** {avg_latency:.0f}ms"
        )
        embed.add_field(name="📈 Overview", value=overview, inline=False)

        # Channel breakdown
        if channel_counts:
            ch_lines = []
            for cid, cnt in sorted(channel_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                ch = self.bot.get_channel(cid)
                name = f"#{ch.name}" if ch else f"Channel {cid}"
                ch_lines.append(f"{name}: {cnt}")
            embed.add_field(
                name="📺 Top Channels",
                value="\n".join(ch_lines),
                inline=True,
            )

        # Recent questions
        if top_qs:
            q_lines = []
            for r in top_qs:
                icon = "✅" if r.action == "auto_reply" else "🟠"
                q_lines.append(f"{icon} {r.question[:80]}")
            embed.add_field(
                name="❓ Recent Questions",
                value="\n".join(q_lines),
                inline=False,
            )

        # Unanswered questions needing owner attention
        if unanswered:
            u_lines = [f"• {r.question[:80]}" for r in unanswered]
            embed.add_field(
                name="🔴 Forwarded / Unanswered",
                value="\n".join(u_lines),
                inline=False,
            )

        if total == 0:
            embed.add_field(
                name="💤 Quiet Day",
                value="No questions received in the last 24 hours.",
                inline=False,
            )

        embed.set_footer(text="Daily Digest • Auto-generated")
        return embed
