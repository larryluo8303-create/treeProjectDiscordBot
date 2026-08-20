"""Resend a GPT summary for an already-ingested YouTube video to Discord.

Usage:
  python scripts/resend_youtube_summary.py
  python scripts/resend_youtube_summary.py --video-id nTWo8Wv7Jao
  python scripts/resend_youtube_summary.py --video-id nTWo8Wv7Jao --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

import aiohttp
import openai

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.config import (
    CHROMADB_COLLECTION,
    CHROMADB_PATH,
    DISCORD_BOT_TOKEN,
    LLM_MODEL,
    YOUTUBE_SUMMARY_CHANNELS,
)
from bot.utils import data_path
from ingestion.ingest import _get_chromadb_collection

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

_LAST_VIDEO_FILE = data_path(
    os.getenv("YOUTUBE_LAST_VIDEO_FILE", "data/youtube_last_video.json")
)


def _load_last_video() -> dict:
    try:
        with open(_LAST_VIDEO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _fetch_transcript_from_chromadb(video_id: str) -> str:
    collection = _get_chromadb_collection(CHROMADB_PATH, CHROMADB_COLLECTION)
    result = collection.get(
        where={"video_id": video_id},
        include=["documents", "metadatas"],
    )

    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    if not docs:
        raise RuntimeError(
            f"No ChromaDB documents found for video_id={video_id}. "
            "Run ingestion first."
        )

    chunks: list[tuple[int, str]] = []
    for doc, meta in zip(docs, metas):
        meta = meta or {}
        chunks.append((int(meta.get("chunk_index", 0)), doc))

    chunks.sort(key=lambda item: item[0])
    return "\n\n".join(text for _, text in chunks)


async def _generate_summary(
    client: openai.AsyncOpenAI,
    title: str,
    transcript_text: str,
) -> str:
    text = transcript_text
    if len(text) > 6000:
        text = text[:6000] + "..."

    prompt = (
        f"以下是 YouTube 视频《{title}》的字幕内容。"
        f"请用中文写一篇 300-500 字的摘要，涵盖视频的核心观点和要点。"
        f"要求简洁、专业、适合股市投资者阅读。\n\n"
        f"字幕内容：\n{text}"
    )

    resp = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.5,
    )
    summary = (resp.choices[0].message.content or "").strip()
    if not summary:
        raise RuntimeError("OpenAI returned an empty summary")
    return summary


async def _post_summary(
    title: str,
    summary: str,
    video_url: str,
    channel_ids: list[int],
) -> None:
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN is not configured")

    embed = {
        "title": f"📺 视频摘要 — {title}",
        "description": summary[:4096],
        "color": 0x57F287,
        "url": video_url,
        "footer": {"text": "由 AI 自动生成的视频内容摘要"},
    }

    from bot.acquisition import rest_cta_components
    payload: dict = {"embeds": [embed]}
    components = rest_cta_components()
    if components:
        payload["components"] = components

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    posted = False

    async with aiohttp.ClientSession() as session:
        for cid in channel_ids:
            url = f"https://discord.com/api/v10/channels/{cid}/messages"
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.error(
                        "Failed to post to channel %d (%s): %s",
                        cid,
                        resp.status,
                        body[:300],
                    )
                    continue
                logger.info("Summary posted to channel %d", cid)
                posted = True

    if not posted:
        raise RuntimeError("Failed to post summary to any configured channel")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Resend YouTube video summary to Discord")
    parser.add_argument("--video-id", help="YouTube video ID (default: latest from data file)")
    parser.add_argument("--title", help="Video title override")
    parser.add_argument("--dry-run", action="store_true", help="Generate summary only; do not post")
    args = parser.parse_args()

    last_video = _load_last_video()
    video_id = args.video_id or last_video.get("video_id")
    if not video_id:
        raise SystemExit("No video ID provided and youtube_last_video.json is empty.")

    title = args.title or last_video.get("title") or video_id
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    channel_ids = YOUTUBE_SUMMARY_CHANNELS
    if not channel_ids:
        raise SystemExit("YOUTUBE_SUMMARY_CHANNELS is not configured.")

    logger.info("Fetching transcript for %s from ChromaDB ...", video_id)
    transcript = _fetch_transcript_from_chromadb(video_id)
    logger.info("Transcript loaded (%d chars)", len(transcript))

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not configured.")

    openai_client = openai.AsyncOpenAI()
    logger.info("Generating GPT summary ...")
    summary = await _generate_summary(openai_client, title, transcript)
    logger.info("Summary generated (%d chars)", len(summary))

    if args.dry_run:
        print("\n--- SUMMARY (dry run) ---\n")
        print(summary)
        return

    logger.info("Posting to channel(s): %s", ", ".join(str(cid) for cid in channel_ids))
    await _post_summary(title, summary, video_url, channel_ids)
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
