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
from discord import app_commands
from discord.ext import commands, tasks

from bot.config import (
    OWNER_USER_ID,
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
        self._resend_lock = asyncio.Lock()

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
        transcript_text = ""
        if YOUTUBE_AUTO_INGEST:
            try:
                inserted, transcript_text = await self._ingest_video(latest_id, latest["link"])
                logger.info("YouTube auto-ingest: %d documents added for %s", inserted, latest_id)
            except Exception as exc:
                logger.warning("YouTube auto-ingest failed for %s: %s", latest_id, exc)

        # Try to fetch transcript from ChromaDB if ingest didn't return one
        if not transcript_text:
            transcript_text = await self._fetch_transcript_from_db(latest_id)

        # Always attempt to post a summary to YOUTUBE_SUMMARY_CHANNELS
        await self._generate_and_post_summary(latest["title"], latest["link"], transcript_text)

    async def _fetch_transcript_from_db(self, video_id: str) -> str:
        """Try to load an already-ingested transcript from ChromaDB."""
        try:
            from ingestion.ingest import _get_chromadb_collection
            from bot.config import CHROMADB_PATH, CHROMADB_COLLECTION

            collection = await asyncio.to_thread(
                _get_chromadb_collection, CHROMADB_PATH, CHROMADB_COLLECTION,
            )
            result = await asyncio.to_thread(
                collection.get,
                where={"video_id": video_id},
                include=["documents", "metadatas"],
            )
            docs = result.get("documents") or []
            metas = result.get("metadatas") or []
            if not docs:
                return ""

            chunks: list[tuple[int, str]] = []
            for doc, meta in zip(docs, metas):
                meta = meta or {}
                chunks.append((int(meta.get("chunk_index", 0)), doc))
            chunks.sort(key=lambda item: item[0])
            text = "\n\n".join(t for _, t in chunks)
            logger.info("YouTube summary: loaded transcript from ChromaDB (%d chars) for %s", len(text), video_id)
            return text
        except Exception as exc:
            logger.warning("YouTube summary: failed to fetch transcript from ChromaDB for %s: %s", video_id, exc)
            return ""

    async def _generate_and_post_summary(
        self, title: str, video_url: str, transcript_text: str
    ) -> None:
        """Generate a GPT summary if transcript is available, then post to Discord.

        Posts a fallback notification even when no transcript is available.
        """
        summary: str | None = None
        if transcript_text and self._openai:
            try:
                summary = await self._summarize_video(title, transcript_text)
            except Exception as exc:
                logger.warning("YouTube summary GPT call failed for '%s': %s", title, exc)
        elif not self._openai:
            logger.warning("YouTube summary: OpenAI client missing — posting notification only")

        if summary:
            await self._post_summary(title, summary, video_url)
        else:
            await self._post_new_video_notification(title, video_url)

    async def _post_new_video_notification(self, title: str, video_url: str) -> None:
        """Post a simple 'new video' embed when no GPT summary is available."""
        summary_channels = YOUTUBE_SUMMARY_CHANNELS
        if not summary_channels:
            summary_channels = YOUTUBE_LESSON_PUSH_CHANNELS if YOUTUBE_LESSON_PUSH_CHANNELS else list(PROMO_CHANNEL_IDS)
        if not summary_channels:
            logger.warning("YouTube notification: no channels configured — skipping")
            return

        embed = discord.Embed(
            title=f"📺 新视频 — {title}",
            description=(
                f"频道主发布了新视频！点击观看：\n\n"
                f"🔗 {video_url}\n\n"
                f"AI 摘要暂时无法生成，请直接观看视频。"
            ),
            color=discord.Color.blue(),
            url=video_url,
        )

        from bot.utils import resolve_channel
        for cid in summary_channels:
            ch = await resolve_channel(self.bot, cid)
            if ch is None or not hasattr(ch, "send"):
                logger.warning("YouTube notification: channel %d not found or not messageable", cid)
                continue
            try:
                await ch.send(embed=embed)
                logger.info("YouTube new-video notification posted to channel %d", cid)
            except Exception as exc:
                logger.warning("YouTube notification: failed to post to %d: %s", cid, exc)

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
            content = resp.choices[0].message.content
            summary = (content or "").strip()
            if not summary:
                return None
            logger.info("YouTube summary generated (%d chars)", len(summary))
            return summary
        except Exception as exc:
            logger.warning("YouTube summary GPT call failed: %s", exc)
            return None

    async def _post_summary(
        self,
        title: str,
        summary: str,
        video_url: str,
        *,
        from_title: bool = False,
    ) -> int:
        """Post the GPT summary as a Discord Embed to YOUTUBE_SUMMARY_CHANNELS.

        Returns the number of channels successfully posted to.
        """
        summary_channels = YOUTUBE_SUMMARY_CHANNELS
        if not summary_channels:
            summary_channels = YOUTUBE_LESSON_PUSH_CHANNELS if YOUTUBE_LESSON_PUSH_CHANNELS else list(PROMO_CHANNEL_IDS)
        if not summary_channels:
            logger.warning("YouTube summary: no channels configured — skipping post")
            return 0

        # Discord embed limits: title 256, description 4096
        safe_title = (title or "未命名视频")[:250]
        safe_summary = summary[:4096] if summary else ""

        embed = discord.Embed(
            title=f"📺 视频摘要 — {safe_title}",
            description=safe_summary,
            color=discord.Color.gold() if from_title else discord.Color.green(),
            url=video_url,
        )
        if from_title:
            embed.set_footer(text="由 AI 根据视频标题生成的预告式摘要（完整字幕暂不可用）")
        else:
            embed.set_footer(text="由 AI 自动生成的视频内容摘要")

        from bot.acquisition import build_cta_view, record_funnel
        from bot.utils import resolve_channel
        view = build_cta_view()

        posted = 0
        for cid in summary_channels:
            ch = await resolve_channel(self.bot, cid)
            if ch is None or not hasattr(ch, "send"):
                logger.warning("YouTube summary: channel %d not found or not messageable", cid)
                continue
            try:
                await ch.send(embed=embed, view=view)
                record_funnel("cta_posts")
                posted += 1
                logger.info("YouTube summary posted to channel %d", cid)
            except Exception as exc:
                logger.warning("YouTube summary: failed to post to %d: %s", cid, exc)
        return posted

    # ── Slash command ─────────────────────────────────────────────────────

    @app_commands.command(
        name="resend_summary",
        description="[Owner] 补发 YouTube 视频摘要到指定频道",
    )
    @app_commands.describe(
        video_url="YouTube 视频链接（留空则使用最近一次检测到的视频）",
        title="视频标题（留空则自动获取）",
    )
    async def resend_summary_cmd(
        self,
        interaction: discord.Interaction,
        video_url: str | None = None,
        title: str | None = None,
    ) -> None:
        if interaction.user.id != OWNER_USER_ID:
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        async def _set_status(msg: str) -> None:
            try:
                await interaction.edit_original_response(content=msg)
            except Exception:
                try:
                    await interaction.followup.send(msg, ephemeral=True)
                except Exception:
                    logger.debug("resend_summary: failed to update status message")

        try:
            await asyncio.wait_for(self._resend_lock.acquire(), timeout=0.05)
        except TimeoutError:
            await _set_status("已有补发任务进行中，请稍后再试。")
            return

        try:
            # Resolve video ID and title
            from_title = False
            if video_url:
                from ingestion.ingest_youtube import extract_video_id
                video_id = extract_video_id(video_url)
                if not video_id:
                    await _set_status("无法从链接中解析 video ID，请检查链接格式。")
                    return
                if not title:
                    last = _load_last_video()
                    if last.get("video_id") == video_id:
                        title = last.get("title")
            else:
                last = _load_last_video()
                video_id = last.get("video_id")
                title = title or last.get("title")
                if not video_id:
                    await _set_status(
                        "未指定视频链接且无最近检测记录。请使用 `video_url` 参数。"
                    )
                    return

            resolved_url = f"https://www.youtube.com/watch?v={video_id}"
            display_title = title or video_id

            await _set_status(f"🔍 检查 ChromaDB 中是否已有视频 `{video_id}` 的转录...")
            transcript_text = await self._fetch_transcript_from_db(video_id)

            if not transcript_text:
                await _set_status(
                    "📥 ChromaDB 中未找到转录，正在自动导入（Whisper 可能需要 1-2 分钟）..."
                )
                try:
                    inserted, transcript_text = await self._ingest_video(video_id, resolved_url)
                    if transcript_text:
                        await _set_status(
                            f"✅ 导入完成（{inserted} 文档 / {len(transcript_text)} 字），正在生成摘要..."
                        )
                    else:
                        from_title = True
                        await _set_status("⚠️ 导入未获得转录，将基于标题生成摘要...")
                except Exception as exc:
                    logger.warning("resend_summary: ingest failed for %s: %s", video_id, exc)
                    from_title = True
                    await _set_status("⚠️ 自动导入失败，将基于标题生成摘要...")

            if not self._openai:
                await _set_status("❌ OpenAI 客户端未配置，无法生成摘要。")
                return

            if transcript_text and not from_title:
                await _set_status("🤖 正在用 GPT 生成摘要...")
                summary = await self._summarize_video(display_title, transcript_text)
            else:
                from_title = True
                await _set_status("🤖 正在根据标题生成预告式摘要...")
                summary = await self._summarize_from_title(display_title)

            if not summary:
                await _set_status("❌ GPT 摘要生成失败，请检查日志。")
                return

            posted = await self._post_summary(
                display_title, summary, resolved_url, from_title=from_title,
            )
            if posted <= 0:
                await _set_status(
                    f"❌ 摘要已生成（{len(summary)} 字），但未能发送到任何频道。"
                    f"请检查 `YOUTUBE_SUMMARY_CHANNELS` 配置与机器人权限。"
                )
                return

            kind = "（基于标题）" if from_title else ""
            await _set_status(
                f"✅ 摘要已发送到 {posted} 个频道{kind}！\n"
                f"📺 **{display_title}**\n字数: {len(summary)}"
            )
        finally:
            self._resend_lock.release()

    async def _summarize_from_title(self, title: str) -> str | None:
        """Generate a preview-style summary based on the video title only."""
        if not self._openai:
            return None
        prompt = (
            f"根据以下 YouTube 视频标题，写一段 150-300 字的预告式摘要。"
            f"标题中包含的关键词和交易信号信息要提取出来，帮助观众理解视频核心内容。"
            f"要求简洁、专业、适合股市投资者阅读。\n\n"
            f"视频标题：{title}"
        )
        try:
            resp = await self._openai.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.5,
            )
            content = resp.choices[0].message.content
            summary = (content or "").strip()
            if not summary:
                return None
            logger.info("YouTube summary (from title) generated (%d chars)", len(summary))
            return summary
        except Exception as exc:
            logger.warning("YouTube summary (from title) GPT call failed: %s", exc)
            return None
