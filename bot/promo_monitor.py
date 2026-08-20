"""Promo monitor — watches a source channel for owner messages and
auto-creates a daily-repeating ``schedule_promo`` with @everyone mention,
valid for a configurable duration (default 90 days / 3 months).

When the owner posts a new message in the source channel:
1. Cancels all previously auto-created promos (source == "promo_monitor").
2. Creates a new daily promo that fires at ``PROMO_PUSH_HOUR`` (ET / UTC-4)
   with @everyone mention and expires after ``PROMO_DURATION_DAYS``.

Configurable via env:
- PROMO_MONITOR_ENABLED    (default false)
- PROMO_SOURCE_CHANNEL_ID  (channel where owner posts promo content)
- PROMO_PUSH_HOUR          (hour in ET / UTC-4 to push daily, default 16)
- PROMO_DURATION_DAYS      (days before auto-cancel, default 90)
- PROMO_PUSH_CHANNELS      (comma-separated target channel IDs, falls back to PROMO_CHANNEL_IDS)
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from bot.config import (
    OWNER_USER_ID,
    PROMO_CHANNEL_IDS,
    PROMO_DURATION_DAYS,
    PROMO_MONITOR_ENABLED,
    PROMO_PUSH_CHANNELS,
    PROMO_PUSH_HOUR,
    PROMO_SOURCE_CHANNEL_ID,
)
from bot.scheduler import _load_json, _save_json, PROMOS_FILE

logger = logging.getLogger(__name__)

# Eastern Time (DST-aware)
_ET = ZoneInfo("America/New_York")

# Tag used to identify auto-created promos
PROMO_MONITOR_SOURCE = "promo_monitor"


# ── Helpers ────────────────────────────────────────────────────────────────

def _next_push_time(hour: int) -> datetime:
    """Return the next occurrence of ``hour`` in ET (UTC-4).

    ``hour`` is clamped to 0-23.
    """
    hour = max(0, min(23, hour))
    now_et = datetime.now(_ET)
    target = now_et.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now_et:
        target += timedelta(days=1)
    return target


def create_auto_promo(
    title: str,
    description: str,
    channel_ids: list[int],
    push_hour: int,
    duration_days: int,
    created_by: int = 0,
    url: str = "",
    image_url: str = "",
) -> dict:
    """Cancel old auto promos and create a new daily-repeating one with @everyone.

    Performs cancel + create in a single load/save cycle.
    """
    scheduled_at = _next_push_time(push_hour)
    expires_at = scheduled_at + timedelta(days=duration_days)

    # Single load → cancel old + append new → single save
    promos = _load_json(PROMOS_FILE)
    cancelled = 0
    for p in promos:
        if p.get("source") == PROMO_MONITOR_SOURCE and not p.get("cancelled"):
            p["cancelled"] = True
            cancelled += 1
    if cancelled:
        logger.info("Promo monitor: cancelled %d previous auto-promo(s)", cancelled)

    promo = {
        "id": f"promo_{uuid.uuid4().hex[:8]}",
        "type": "promo",
        "title": title,
        "description": description,
        "url": url,
        "image_url": image_url,
        "scheduled_at": scheduled_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "repeat": "daily",
        "channel_ids": channel_ids,
        "last_posted": None,
        "cancelled": False,
        "created_by": created_by,
        "source": PROMO_MONITOR_SOURCE,
        "mention_everyone": True,
    }
    promos.append(promo)
    _save_json(PROMOS_FILE, promos)

    logger.info(
        "Promo monitor: created daily promo %s for '%s' at %02d:00 ET, expires %s",
        promo["id"], title, push_hour, expires_at.strftime("%Y-%m-%d"),
    )
    return promo


# ── Cog ────────────────────────────────────────────────────────────────────

class PromoMonitorCog(commands.Cog):
    """Watches a source channel for owner messages and auto-creates daily promos."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        if not PROMO_MONITOR_ENABLED:
            return
        if not PROMO_SOURCE_CHANNEL_ID:
            logger.warning("Promo monitor enabled but PROMO_SOURCE_CHANNEL_ID is empty — skipping")
            return
        logger.info(
            "Promo monitor started (source_channel=%d, push_hour=%d ET, duration=%dd)",
            PROMO_SOURCE_CHANNEL_ID, PROMO_PUSH_HOUR, PROMO_DURATION_DAYS,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not PROMO_MONITOR_ENABLED:
            return
        if not PROMO_SOURCE_CHANNEL_ID:
            return
        # Only react to owner messages in the source channel
        if message.author.bot:
            return
        if message.author.id != OWNER_USER_ID:
            return
        if message.channel.id != PROMO_SOURCE_CHANNEL_ID:
            return
        if not message.content or not message.content.strip():
            return

        logger.info(
            "Promo monitor: owner posted in source channel (msg_id=%s, len=%d)",
            message.id, len(message.content),
        )

        # Determine target channels
        channel_ids = PROMO_PUSH_CHANNELS if PROMO_PUSH_CHANNELS else list(PROMO_CHANNEL_IDS)
        if not channel_ids:
            logger.warning("Promo monitor: no push channels configured — skipping")
            return

        # Extract content — first line as title, rest as description
        lines = message.content.strip().split("\n", 1)
        title = lines[0].strip()
        description = lines[1].strip() if len(lines) > 1 else title

        # Check for image attachments — use proxy_url (longer-lived CDN) if available
        image_url = ""
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                image_url = att.proxy_url or att.url
                break

        promo = create_auto_promo(
            title=title,
            description=description,
            channel_ids=channel_ids,
            push_hour=PROMO_PUSH_HOUR,
            duration_days=PROMO_DURATION_DAYS,
            created_by=message.author.id,
            image_url=image_url,
        )

        # Confirm to the owner in the source channel
        await message.reply(
            f"✅ 活動推廣已排程！\n"
            f"**ID:** `{promo['id']}`\n"
            f"**標題:** {title}\n"
            f"**推送時間:** 每天 {PROMO_PUSH_HOUR}:00 ET\n"
            f"**有效期:** {PROMO_DURATION_DAYS} 天\n"
            f"**@everyone:** 是\n"
            f"（舊的自動推廣已自動取消）",
            mention_author=False,
        )
