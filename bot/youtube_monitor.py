"""YouTube new-video monitor — polls the channel RSS feed and auto-creates
a daily-repeating ``schedule_lesson`` whenever a new video is published.

When a new video is detected the monitor:
1. Cancels all previously auto-created lessons (source == "youtube_monitor").
2. Creates a new lesson that fires daily at ``YOUTUBE_LESSON_PUSH_HOUR``
   (UTC-4 / Eastern) and posts to ``YOUTUBE_LESSON_PUSH_CHANNELS``
   (falls back to ``PROMO_CHANNEL_IDS``).

Configurable via env:
- YOUTUBE_MONITOR_ENABLED  (default false)
- YOUTUBE_CHANNEL_ID       (your YouTube channel ID, e.g. UCxxxxxxxxxx)
- YOUTUBE_CHECK_HOUR        (hour in ET for the daily check, default 9)
- YOUTUBE_CHECK_MINUTE      (minute in ET for the daily check, default 30)
- YOUTUBE_LESSON_PUSH_HOUR  (hour in ET / UTC-4 to push daily, default 16)
- YOUTUBE_LESSON_PUSH_CHANNELS (comma-separated Discord channel IDs, optional)
- YOUTUBE_AUTO_INGEST       (auto-ingest transcript to KB, default true)
- YOUTUBE_SUMMARY_CHANNELS  (channels for GPT summary, optional)
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import aiohttp
import discord
import openai
from discord.ext import commands, tasks

from bot.config import (
    PROMO_CHANNEL_IDS,
    YOUTUBE_AUTO_INGEST,
    YOUTUBE_CHECK_HOUR,
    YOUTUBE_CHECK_MINUTE,
    YOUTUBE_LESSON_PUSH_CHANNELS,
    YOUTUBE_LESSON_PUSH_HOUR,
    YOUTUBE_MONITOR_ENABLED,
    YOUTUBE_CHANNEL_ID,
    YOUTUBE_SUMMARY_CHANNELS,
    LLM_MODEL,
)
from bot.scheduler import _load_json, _save_json, LESSONS_FILE
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

_YT_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_LAST_VIDEO_FILE = data_path(os.getenv("YOUTUBE_LAST_VIDEO_FILE", "data/youtube_last_video.json"))

# Namespace used in YouTube Atom feed
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_YT_NS = "{http://www.youtube.com/xml/schemas/2015}"

# Eastern Time (DST-aware)
_ET = ZoneInfo("America/New_York")

# Tag used to identify auto-created lessons
YOUTUBE_LESSON_SOURCE = "youtube_monitor"


# ── Persistence helpers ─────────────────────────────────────────────────────

def _load_last_video() -> dict:
    """Return ``{"video_id": "...", "title": "..."}`` or empty dict."""
    try:
        with open(_LAST_VIDEO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_last_video(video_id: str, title: str) -> None:
    atomic_json_write(_LAST_VIDEO_FILE, {"video_id": video_id, "title": title})


# ── RSS helpers ─────────────────────────────────────────────────────────────

def parse_feed(xml_text: str) -> list[dict]:
    """Parse YouTube Atom XML and return a list of video dicts (newest first).

    Each dict has keys: ``video_id``, ``title``, ``link``, ``published``.
    """
    root = ElementTree.fromstring(xml_text)
    entries: list[dict] = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        video_id_el = entry.find(f"{_YT_NS}videoId")
        title_el = entry.find(f"{_ATOM_NS}title")
        link_el = entry.find(f"{_ATOM_NS}link")
        published_el = entry.find(f"{_ATOM_NS}published")

        if video_id_el is None or title_el is None:
            continue

        entries.append({
            "video_id": (video_id_el.text or "").strip(),
            "title": (title_el.text or "").strip(),
            "link": link_el.get("href", "") if link_el is not None else "",
            "published": (published_el.text or "").strip() if published_el is not None else "",
        })
    return entries


# ── Lesson management helpers ───────────────────────────────────────────────

def _cancel_youtube_lessons() -> int:
    """Cancel all existing lessons created by the YouTube monitor. Returns count."""
    lessons = _load_json(LESSONS_FILE)
    cancelled = 0
    for ls in lessons:
        if ls.get("source") == YOUTUBE_LESSON_SOURCE and not ls.get("cancelled"):
            ls["cancelled"] = True
            cancelled += 1
    if cancelled:
        _save_json(LESSONS_FILE, lessons)
    return cancelled


def _next_push_time(hour: int) -> datetime:
    """Return the next occurrence of ``hour`` in ET (UTC-4).

    If that hour has already passed today, schedule for tomorrow.
    ``hour`` is clamped to 0-23.
    """
    hour = max(0, min(23, hour))
    now_et = datetime.now(_ET)
    target = now_et.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now_et:
        target += timedelta(days=1)
    return target


def create_youtube_lesson(
    title: str,
    video_url: str,
    channel_ids: list[int],
    push_hour: int,
    created_by: int = 0,
) -> dict:
    """Cancel old YouTube lessons and create a new daily-repeating one.

    Performs cancel + create in a single load/save cycle to avoid race
    conditions from double-writing the lessons file.
    """
    scheduled_at = _next_push_time(push_hour)

    content = (
        f"🎬 频道主发布了新视频！\n\n"
        f"**{title}**\n\n"
        f"🔗 观看链接: {video_url}\n\n"
        f"记得点赞、订阅、开启小铃铛！🔔"
    )

    # Single load → cancel old + append new → single save
    lessons = _load_json(LESSONS_FILE)
    cancelled = 0
    for ls in lessons:
        if ls.get("source") == YOUTUBE_LESSON_SOURCE and not ls.get("cancelled"):
            ls["cancelled"] = True
            cancelled += 1
    if cancelled:
        logger.info("YouTube monitor: cancelled %d previous auto-lesson(s)", cancelled)

    lesson = {
        "id": f"lesson_{uuid.uuid4().hex[:8]}",
        "title": title,
        "content": content,
        "scheduled_at": scheduled_at.isoformat(),
        "repeat": "daily",
        "channel_ids": channel_ids,
        "last_posted": None,
        "cancelled": False,
        "created_by": created_by,
        "source": YOUTUBE_LESSON_SOURCE,
    }
    lessons.append(lesson)
    _save_json(LESSONS_FILE, lessons)

    logger.info(
        "YouTube monitor: created daily lesson %s for '%s' at %02d:00 ET",
        lesson["id"], title, push_hour,
    )
    return lesson


# ── Cog ─────────────────────────────────────────────────────────────────────

class YouTubeMonitorCog(commands.Cog):
    """Polls YouTube RSS for new videos and auto-creates daily lesson pushes.

    When a new video is detected and ``YOUTUBE_AUTO_INGEST`` is enabled, the
    cog also ingests the video transcript into ChromaDB and posts a
    GPT-generated summary to ``YOUTUBE_SUMMARY_CHANNELS``.
    """

    def __init__(self, bot: commands.Bot, openai_client: openai.AsyncOpenAI | None = None) -> None:
        self.bot = bot
        self._openai = openai_client
        self._last_video = _load_last_video()
        self._session: aiohttp.ClientSession | None = None
        self._last_check_date: str | None = None  # "YYYY-MM-DD" of last daily trigger

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not YOUTUBE_MONITOR_ENABLED:
            return
        if not YOUTUBE_CHANNEL_ID:
            logger.warning("YouTube monitor enabled but YOUTUBE_CHANNEL_ID is empty — skipping")
            return
        if self._daily_check.is_running():
            return
        logger.info(
            "YouTube monitor started (channel=%s, daily_check=%02d:%02d ET, push_hour=%d ET)",
            YOUTUBE_CHANNEL_ID, YOUTUBE_CHECK_HOUR, YOUTUBE_CHECK_MINUTE, YOUTUBE_LESSON_PUSH_HOUR,
        )
        # Run initial check immediately, then start the daily loop
        try:
            await self._check_for_new_video()
        except Exception as exc:
            logger.warning("YouTube monitor: initial poll error: %s", exc)
        self._daily_check.start()

    async def cog_unload(self) -> None:
        self._daily_check.cancel()
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    @tasks.loop(seconds=60)
    async def _daily_check(self) -> None:
        """Check once per minute if it's the configured daily check time."""
        now_et = datetime.now(_ET)
        if now_et.hour != YOUTUBE_CHECK_HOUR or now_et.minute != YOUTUBE_CHECK_MINUTE:
            return
        today_str = now_et.strftime("%Y-%m-%d")
        if self._last_check_date == today_str:
            return  # already checked today
        self._last_check_date = today_str
        logger.info("YouTube monitor: daily check at %02d:%02d ET", YOUTUBE_CHECK_HOUR, YOUTUBE_CHECK_MINUTE)
        try:
            await self._check_for_new_video()
        except Exception as exc:
            logger.warning("YouTube monitor daily check error: %s", exc)

    async def _check_for_new_video(self) -> None:
        session = await self._get_session()
        url = _YT_RSS_URL.format(channel_id=YOUTUBE_CHANNEL_ID)
        async with session.get(url) as resp:
            if resp.status != 200:
                logger.warning("YouTube RSS returned status %d", resp.status)
                return
            xml_text = await resp.text()

        entries = parse_feed(xml_text)
        if not entries:
            logger.warning("YouTube monitor: RSS feed returned no entries")
            return

        latest = entries[0]
        latest_id = latest["video_id"]
        logger.debug("YouTube monitor: latest video=%s title=%s", latest_id, latest["title"][:60])

        # No new video
        if latest_id == self._last_video.get("video_id"):
            logger.debug("YouTube monitor: no new video (same as last=%s)", latest_id)
            return

        # First run or new video detected
        if not self._last_video:
            logger.info("YouTube monitor: first run — creating lesson for latest video: %s", latest["title"])
        else:
            logger.info("YouTube monitor: new video detected — %s", latest["title"])

        channel_ids = YOUTUBE_LESSON_PUSH_CHANNELS if YOUTUBE_LESSON_PUSH_CHANNELS else list(PROMO_CHANNEL_IDS)
        if not channel_ids:
            logger.warning("YouTube monitor: no push channels configured — skipping lesson creation")
            _save_last_video(latest_id, latest["title"])
            self._last_video = {"video_id": latest_id, "title": latest["title"]}
            return

        create_youtube_lesson(
            title=latest["title"],
            video_url=latest["link"],
            channel_ids=channel_ids,
            push_hour=YOUTUBE_LESSON_PUSH_HOUR,
        )

        _save_last_video(latest_id, latest["title"])
        self._last_video = {"video_id": latest_id, "title": latest["title"]}

        # ── Auto-ingest + GPT summary ──────────────────────────────────
        if YOUTUBE_AUTO_INGEST:
            try:
                inserted, transcript_text = await self._ingest_video(latest_id, latest["link"])
                logger.info("YouTube auto-ingest: %d documents added for %s", inserted, latest_id)

                if inserted > 0 and self._openai and transcript_text:
                    summary = await self._summarize_video(latest["title"], transcript_text)
                    if summary:
                        await self._post_summary(latest["title"], summary, latest["link"])
                elif inserted > 0 and not transcript_text:
                    logger.warning(
                        "YouTube summary: skipped for %s — no transcript text available",
                        latest_id,
                    )
                elif inserted > 0 and not self._openai:
                    logger.warning("YouTube summary: skipped for %s — OpenAI client missing", latest_id)
            except Exception as exc:
                logger.warning("YouTube auto-ingest/summary failed for %s: %s", latest_id, exc)

    # ── Auto-ingest helpers ────────────────────────────────────────────────

    async def _ingest_video(self, video_id: str, video_url: str) -> tuple[int, str]:
        """Ingest a YouTube video transcript into ChromaDB (runs in thread).

        Returns (documents_inserted, transcript_full_text).
        """
        from ingestion.ingest_youtube import run_youtube_ingestion

        inserted, transcript_texts = await asyncio.to_thread(
            run_youtube_ingestion,
            urls=[video_url],
            whisper_fallback=True,
            whisper_lang="zh",
        )
        full_text = transcript_texts.get(video_id, "")
        return inserted, full_text

    async def _summarize_video(self, title: str, transcript_text: str) -> str | None:
        """Generate a GPT summary from transcript text."""
        if not transcript_text.strip():
            logger.warning("YouTube summary: empty transcript — skipping")
            return None

        # Truncate to ~6000 chars to stay within context window budget
        text = transcript_text
        if len(text) > 6000:
            text = text[:6000] + "..."

        prompt = (
            f"以下是 YouTube 视频《{title}》的字幕内容。"
            f"请用中文写一篇 300-500 字的摘要，涵盖视频的核心观点和要点。"
            f"要求简洁、专业、适合股市投资者阅读。\n\n"
            f"字幕内容：\n{text}"
        )

        try:
            resp = await self._openai.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.5,
            )
            summary = resp.choices[0].message.content.strip()
            logger.info("YouTube summary generated (%d chars)", len(summary))
            return summary
        except Exception as exc:
            logger.warning("YouTube summary GPT call failed: %s", exc)
            return None

    async def _post_summary(self, title: str, summary: str, video_url: str) -> None:
        """Post the GPT summary as a Discord Embed to YOUTUBE_SUMMARY_CHANNELS."""
        summary_channels = YOUTUBE_SUMMARY_CHANNELS
        if not summary_channels:
            summary_channels = YOUTUBE_LESSON_PUSH_CHANNELS if YOUTUBE_LESSON_PUSH_CHANNELS else list(PROMO_CHANNEL_IDS)
        if not summary_channels:
            logger.warning("YouTube summary: no channels configured — skipping post")
            return

        embed = discord.Embed(
            title=f"📺 视频摘要 — {title}",
            description=summary,
            color=discord.Color.green(),
            url=video_url,
        )
        embed.set_footer(text="由 AI 自动生成的视频内容摘要")

        from bot.acquisition import build_cta_view, record_funnel
        from bot.utils import resolve_channel
        view = build_cta_view()

        for cid in summary_channels:
            ch = await resolve_channel(self.bot, cid)
            if ch is None or not hasattr(ch, "send"):
                logger.warning("YouTube summary: channel %d not found or not messageable", cid)
                continue
            try:
                await ch.send(embed=embed, view=view)
                record_funnel("cta_posts")
                logger.info("YouTube summary posted to channel %d", cid)
            except Exception as exc:
                logger.warning("YouTube summary: failed to post to %d: %s", cid, exc)
