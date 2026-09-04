"""Jin10 market flash news feed — polls jin10.com and posts to Discord channels.

Configurable via:
- NEWS_FEED_ENABLED (default false)
- NEWS_CHANNEL_IDS (comma-separated Discord channel IDs)
- NEWS_POLL_INTERVAL_SECONDS (default 30)
- NEWS_IMPORTANT_ONLY (default true — only push important/starred items)
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord.ext import commands

from bot.config import (
    NEWS_BACKFILL_HOURS,
    NEWS_CHANNEL_IDS,
    NEWS_FEED_ENABLED,
    NEWS_IMPORTANT_ONLY,
    NEWS_POLL_INTERVAL_SECONDS,
    OWNER_USER_ID,
)
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

JIN10_API_URL = "https://flash-api.jin10.com/get_flash_list"
JIN10_HEADERS = {
    "x-app-id": "bVBF4FyRTn5NJF5n",
    "x-version": "1.0.0",
}
JIN10_PARAMS = {"channel": "-8200", "vip": "1"}

LAST_ID_FILE = data_path(os.getenv("NEWS_LAST_ID_FILE", "data/jin10_last_id.json"))

# Timezone constants for time conversion
_TZ_BEIJING = ZoneInfo("Asia/Shanghai")
_TZ_TORONTO = ZoneInfo("America/Toronto")

# Title extraction: 【title】rest of content
_TITLE_RE = re.compile(r"^【(.*?)】")

# HTML tag patterns
_BR_RE = re.compile(r"<br\s*/?>") 
_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_NL_RE = re.compile(r"\n{3,}")

# Consecutive API errors before alerting the owner
_ERROR_ALERT_THRESHOLD = 10

# Maximum pages to fetch during backfill (safety cap)
_BACKFILL_MAX_PAGES = 50


def _clean_html(text: str) -> str:
    """Strip HTML tags from Jin10 content, converting <br> to newlines."""
    if not text:
        return ""
    # Replace <br/> and <br> with newline
    text = _BR_RE.sub("\n", text)
    # Remove all remaining HTML tags
    text = _TAG_RE.sub("", text)
    # Collapse multiple blank lines into one
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def _extract_items(payload: dict) -> list[dict]:
    """Extract flash items from Jin10 API response, handling both nesting formats."""
    data = payload.get("data")
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, list):
            return inner
    if isinstance(data, list):
        return data
    return []


def _load_last_id() -> str:
    """Load the last seen Jin10 flash ID from disk."""
    try:
        with open(LAST_ID_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        last_id = data.get("last_id", "")
        logger.info("Loaded Jin10 last_id=%s from %s", last_id, LAST_ID_FILE)
        return last_id
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        logger.info("No Jin10 last_id file found at %s", LAST_ID_FILE)
        return ""


def _save_last_id(last_id: str) -> None:
    """Persist the last seen Jin10 flash ID to disk."""
    try:
        atomic_json_write(LAST_ID_FILE, {"last_id": last_id})
    except OSError as exc:
        logger.warning("Failed to save Jin10 last_id: %s", exc)


def extract_title_and_content(raw_content: str) -> tuple[str, str]:
    """Parse 【title】content pattern. Returns (title, body).

    If no 【...】 prefix, title is the first 60 chars of content.
    HTML tags are stripped from both title and body.
    """
    if not raw_content:
        return ("", "")
    match = _TITLE_RE.match(raw_content)
    if match:
        title = _clean_html(match.group(1))
        body = _clean_html(raw_content[match.end():])
        return (title, body if body else title)
    # Fallback: use first 60 chars of cleaned content as title
    cleaned = _clean_html(raw_content)
    return (cleaned[:60], cleaned)


def filter_items(
    items: list[dict],
    last_id: str,
    important_only: bool = True,
) -> list[dict]:
    """Filter Jin10 flash items: dedup by last_id, skip ads, optionally only important.

    Returns items newer than last_id, sorted oldest-first for chronological posting.
    """
    filtered: list[dict] = []
    for item in items:
        item_id = item.get("id", "")
        # Dedup: skip items we've already seen (IDs are chronologically ordered strings)
        if last_id and item_id <= last_id:
            continue
        # Skip ads
        extras = item.get("extras") or {}
        if extras.get("ad"):
            continue
        # Skip type 1 (non-content items)
        if item.get("type") == 1:
            continue
        # Important filter
        if important_only and not item.get("important"):
            continue
        # Skip items with empty content
        data = item.get("data") or {}
        if not data.get("content", "").strip():
            continue
        filtered.append(item)

    # Sort oldest-first so we post in chronological order
    filtered.sort(key=lambda x: x.get("id", ""))
    return filtered


def _convert_beijing_to_toronto(time_str: str) -> str:
    """Convert a Beijing time string to Toronto (Eastern) time.

    Input:  '2026-08-15 10:00:00' (Asia/Shanghai, UTC+8)
    Output: '2026-08-14 22:00:00 ET'
    Returns the original string if parsing fails.
    """
    if not time_str:
        return time_str
    try:
        beijing_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        beijing_dt = beijing_dt.replace(tzinfo=_TZ_BEIJING)
        toronto_dt = beijing_dt.astimezone(_TZ_TORONTO)
        return toronto_dt.strftime("%Y-%m-%d %H:%M:%S ET")
    except (ValueError, TypeError):
        return time_str


def build_embed(item: dict) -> discord.Embed:
    """Build a Discord Embed for an important flash news item."""
    data = item.get("data") or {}
    raw_content = data.get("content", "")
    title, body = extract_title_and_content(raw_content)
    time_str = _convert_beijing_to_toronto(item.get("time", ""))

    embed = discord.Embed(
        title=f"\U0001f534 {title}"[:256],
        description=body,
        color=0xE74C3C,
    )

    # Add image if present
    pic = data.get("pic", "")
    if pic and pic.startswith("http"):
        embed.set_image(url=pic)

    # Add link if present
    link = data.get("link", "")
    if link and link.startswith("http"):
        embed.add_field(name="", value=f"[\u67e5\u770b\u8be6\u60c5]({link})", inline=False)

    embed.set_footer(text=time_str)
    return embed


def build_text(item: dict) -> str:
    """Build a plain text message for a regular flash news item."""
    data = item.get("data") or {}
    content = _clean_html(data.get("content", ""))
    return f"\U0001f4f0 {content}"


class NewsFeedCog(commands.Cog):
    """Polls Jin10 flash API and posts market news to Discord channels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._poll_task: asyncio.Task | None = None
        self._started: bool = False
        self._session: aiohttp.ClientSession | None = None
        self._last_id: str = _load_last_id()
        self._consecutive_errors: int = 0

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not NEWS_FEED_ENABLED:
            return
        if not NEWS_CHANNEL_IDS:
            logger.warning("News feed enabled but NEWS_CHANNEL_IDS is empty — skipping")
            return
        # Backfill missed items on every reconnect / startup (not only the first on_ready).
        if NEWS_BACKFILL_HOURS > 0 and self._last_id:
            logger.info("Jin10 backfill: starting with last_id=%s", self._last_id)
            try:
                await self._backfill_on_startup()
            except Exception as exc:
                logger.warning("Jin10 news feed backfill failed: %s", exc)
            logger.info("Jin10 backfill: finished, last_id now=%s", self._last_id)
        if self._started:
            return
        self._started = True
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop())
            logger.info(
                "Jin10 news feed started (interval=%ds, important_only=%s, channels=%s)",
                NEWS_POLL_INTERVAL_SECONDS,
                NEWS_IMPORTANT_ONLY,
                NEWS_CHANNEL_IDS,
            )

    async def cog_unload(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazily create and return a reusable aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=JIN10_HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def _poll_loop(self) -> None:
        """Background loop: fetch → filter → post, then sleep."""
        try:
            while True:
                await asyncio.sleep(NEWS_POLL_INTERVAL_SECONDS)
                try:
                    await self._fetch_and_post()
                    self._consecutive_errors = 0
                except Exception as exc:
                    self._consecutive_errors += 1
                    logger.warning(
                        "Jin10 news feed error (%d consecutive): %s",
                        self._consecutive_errors,
                        exc,
                    )
                    if self._consecutive_errors == _ERROR_ALERT_THRESHOLD:
                        asyncio.create_task(self._alert_owner(str(exc)))
        except asyncio.CancelledError:
            pass

    def _maybe_advance_last_id(self, candidate_ids: list[str]) -> None:
        """Persist the highest seen Jin10 ID if it moves the cursor forward."""
        valid = [i for i in candidate_ids if i]
        if not valid:
            return
        new_last = max(valid)
        if new_last > self._last_id:
            self._last_id = new_last
            _save_last_id(new_last)

    async def _fetch_and_post(self) -> None:
        """Fetch latest flash news from Jin10 and post new items to channels."""
        session = await self._get_session()
        async with session.get(JIN10_API_URL, params=JIN10_PARAMS) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Jin10 API returned status {resp.status}")
            payload = await resp.json(content_type=None)

        items = _extract_items(payload)

        new_items = filter_items(items, self._last_id, NEWS_IMPORTANT_ONLY)
        all_ids = [it.get("id", "") for it in items if it.get("id")]

        if not new_items:
            # Advance past non-important / filtered items so they are not re-scanned.
            self._maybe_advance_last_id(all_ids)
            return

        posted_ids: list[str] = []
        for item in new_items:
            important = item.get("important")
            if important:
                message = build_embed(item)
            else:
                message = build_text(item)

            posted_to_any = False
            for channel_id in NEWS_CHANNEL_IDS:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden) as exc:
                        logger.warning("News feed: cannot access channel %d (%s)", channel_id, exc)
                        continue

                try:
                    if isinstance(message, discord.Embed):
                        await channel.send(embed=message)
                    else:
                        await channel.send(message, allowed_mentions=discord.AllowedMentions.none())
                    posted_to_any = True
                except (discord.Forbidden, discord.HTTPException) as exc:
                    logger.warning("News feed: failed to post to channel %d: %s", channel_id, exc)

            if posted_to_any:
                item_id = item.get("id", "")
                if item_id:
                    posted_ids.append(item_id)

        if not posted_ids:
            logger.warning("News feed: failed to post any items — not advancing last_id")
            return

        # Only advance after successful posts. If all items posted, also skip
        # non-important items returned in the same API page.
        if len(posted_ids) == len(new_items):
            self._maybe_advance_last_id(all_ids)
        else:
            self._maybe_advance_last_id(posted_ids)

        logger.info("Jin10 news feed: posted %d item(s) to %d channel(s)",
                     len(posted_ids), len(NEWS_CHANNEL_IDS))

    async def _backfill_on_startup(self) -> None:
        """Fetch missed items from the last N hours and post as a batch."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_BACKFILL_HOURS)
        cutoff_beijing = cutoff.astimezone(_TZ_BEIJING).replace(tzinfo=None)

        session = await self._get_session()
        all_missed: list[dict] = []
        seen_ids: set[str] = set()
        current_max_id: str | None = None  # start from latest

        for _page in range(_BACKFILL_MAX_PAGES):
            params = dict(JIN10_PARAMS)
            if current_max_id:
                params["max_id"] = current_max_id

            async with session.get(JIN10_API_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Jin10 backfill: API returned status %d", resp.status)
                    break
                payload = await resp.json(content_type=None)

            items = _extract_items(payload)
            if not items:
                break

            reached_old = False
            for item in items:
                item_id = item.get("id", "")

                # Dedup: skip items already collected (pagination overlap)
                if item_id in seen_ids:
                    continue

                item_time_str = item.get("time", "")
                # Parse item time (Beijing time: "2026-08-15 10:00:00")
                try:
                    item_time = datetime.strptime(item_time_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    continue

                # Stop if we've gone beyond the lookback window
                if item_time < cutoff_beijing:
                    reached_old = True
                    break

                # Only collect items newer than our last seen ID
                if self._last_id and item_id <= self._last_id:
                    reached_old = True
                    break

                seen_ids.add(item_id)
                all_missed.append(item)

            if reached_old:
                break

            # Use the oldest item's ID for pagination
            oldest_id = items[-1].get("id", "")
            if not oldest_id or oldest_id == current_max_id:
                break
            current_max_id = oldest_id

        # Filter: important only, skip ads/type1/empty
        logger.info("Jin10 backfill: collected %d raw items, last_id=%s", len(all_missed), self._last_id)
        if all_missed:
            ids = [it.get("id", "") for it in all_missed]
            logger.info("Jin10 backfill: collected IDs: %s", ids[:10])
        backfill_items = filter_items(all_missed, self._last_id, important_only=NEWS_IMPORTANT_ONLY)
        all_collected_ids = [it.get("id", "") for it in all_missed if it.get("id")]

        if not backfill_items:
            if all_collected_ids:
                self._maybe_advance_last_id(all_collected_ids)
            if all_missed:
                logger.info(
                    "Jin10 backfill: no missed %s items (%d raw item(s) filtered out)",
                    "important" if NEWS_IMPORTANT_ONLY else "",
                    len(all_missed),
                )
            else:
                logger.info("Jin10 backfill: no missed important items found")
            return

        # Cap at a reasonable number to avoid flooding
        max_backfill = 50
        if len(backfill_items) > max_backfill:
            backfill_items = backfill_items[-max_backfill:]  # keep newest N

        # Post header embed
        header_embed = discord.Embed(
            title="\U0001f4cb \u79bb\u7ebf\u671f\u95f4\u91cd\u8981\u5feb\u8baf\u56de\u987e",
            description=(
                f"Bot \u91cd\u65b0\u4e0a\u7ebf\uff0c\u4ee5\u4e0b\u662f\u79bb\u7ebf\u671f\u95f4\u9519\u8fc7\u7684 "
                f"**{len(backfill_items)}** \u6761\u91cd\u8981\u5feb\u8baf\uff1a"
            ),
            color=0x3498DB,
        )

        for channel_id in NEWS_CHANNEL_IDS:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden):
                    continue
            try:
                await channel.send(embed=header_embed)
            except (discord.Forbidden, discord.HTTPException):
                continue

        # Post each missed item
        for item in backfill_items:
            embed = build_embed(item)
            for channel_id in NEWS_CHANNEL_IDS:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden):
                        continue
                try:
                    await channel.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException) as exc:
                    logger.warning("News feed backfill: failed to post to channel %d: %s", channel_id, exc)

        # Update cursor to the max ID across ALL collected items (not just
        # posted ones) so subsequent backfills don't re-post the same items.
        if all_collected_ids:
            self._maybe_advance_last_id(all_collected_ids)

        logger.info(
            "Jin10 backfill: posted %d missed important item(s) to %d channel(s)",
            len(backfill_items),
            len(NEWS_CHANNEL_IDS),
        )

    async def _alert_owner(self, error_msg: str) -> None:
        """DM the owner when the news feed encounters repeated errors."""
        try:
            owner = await self.bot.fetch_user(OWNER_USER_ID)
            if owner:
                embed = discord.Embed(
                    title="\u26a0\ufe0f \u91d1\u5341\u5feb\u8baf\u62c9\u53d6\u5931\u8d25",
                    description=(
                        f"\u8fde\u7eed {_ERROR_ALERT_THRESHOLD} \u6b21\u62c9\u53d6\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u6216 API \u72b6\u6001\u3002\n\n"
                        f"\u6700\u540e\u4e00\u6b21\u9519\u8bef\uff1a`{error_msg[:500]}`"
                    ),
                    color=discord.Color.orange(),
                )
                await owner.send(embed=embed)
        except Exception as exc:
            logger.warning("Failed to alert owner about news feed error: %s", exc)
