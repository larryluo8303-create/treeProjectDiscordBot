"""Fetch YouTube video transcripts and ingest them into ChromaDB.

Usage examples:

  # Single video
  python -m ingestion.ingest_youtube --urls "https://www.youtube.com/watch?v=VIDEO_ID"

  # Multiple videos
  python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" "https://youtu.be/BBB"

  # Read URLs from a text file (one URL per line)
  python -m ingestion.ingest_youtube --url-file my_videos.txt

  # Prefer Chinese transcript, fall back to English
  python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" --lang zh-Hans en
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache

import openai
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.config import (
    CHROMADB_COLLECTION,
    CHROMADB_PATH,
    CHUNK_MAX_TOKENS,
    CHUNK_OVERLAP_TOKENS,
    OPENAI_API_KEY,
)
from ingestion.ingest import _get_chromadb_collection, ingest_to_chromadb
from ingestion.preprocess import chunk_text

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


WHISPER_MAX_BYTES = 24 * 1024 * 1024  # 24 MB — Whisper API hard limit is 25 MB

# ── Helpers ───────────────────────────────────────────────────────────────────


def extract_video_id(url: str) -> str | None:
    """Extract the YouTube video ID from various URL formats."""
    patterns = [
        r"(?:youtube\.com/watch\?.*v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    # If already a raw 11-char ID
    if re.match(r"^[A-Za-z0-9_-]{11}$", url.strip()):
        return url.strip()
    return None


# Backward-compatible alias
_extract_video_id = extract_video_id


def _merge_transcript_segments(segments, gap_seconds: float = 3.0) -> list[str]:
    """Merge short transcript segments into natural paragraphs.

    Segments separated by more than *gap_seconds* become separate paragraphs.
    Accepts both dicts (Whisper) and FetchedTranscriptSnippet objects (v1.x API).
    """
    if not segments:
        return []

    paragraphs: list[str] = []
    current_parts: list[str] = []
    last_end: float = 0.0

    for seg in segments:
        # Support both dict (Whisper) and object (youtube-transcript-api v1.x)
        if isinstance(seg, dict):
            start = seg.get("start", 0.0)
            duration = seg.get("duration", 0.0)
            text = seg.get("text", "").strip()
        else:
            start = getattr(seg, "start", 0.0)
            duration = getattr(seg, "duration", 0.0)
            text = getattr(seg, "text", "").strip()
        if not text:
            continue

        if current_parts and (start - last_end) > gap_seconds:
            paragraphs.append(" ".join(current_parts))
            current_parts = []

        current_parts.append(text)
        last_end = start + duration

    if current_parts:
        paragraphs.append(" ".join(current_parts))

    return paragraphs


# ── Binary resolution helpers ─────────────────────────────────────────────────


def _venv_bin_candidates(name: str) -> list[str]:
    """Return possible binary paths inside the active interpreter's Scripts/bin dir."""
    bindir = os.path.dirname(sys.executable)
    names = [name]
    if sys.platform == "win32":
        names = [f"{name}.exe", name]
    else:
        names = [name, f"{name}.exe"]
    return [os.path.join(bindir, n) for n in names]


@lru_cache(maxsize=1)
def _resolve_yt_dlp() -> str:
    """Return the full path to yt-dlp, preferring the venv Scripts/bin directory."""
    for path in _venv_bin_candidates("yt-dlp"):
        if os.path.isfile(path):
            return path
    system_path = shutil.which("yt-dlp")
    if system_path:
        return system_path
    raise RuntimeError(
        "yt-dlp is not installed. Install it with: pip install 'yt-dlp[default]'"
    )


@lru_cache(maxsize=1)
def _resolve_ffmpeg() -> str:
    """Return the full path to ffmpeg (venv → imageio-ffmpeg → PATH)."""
    for path in _venv_bin_candidates("ffmpeg"):
        if os.path.isfile(path):
            return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, FileNotFoundError, RuntimeError):
        pass
    system_path = shutil.which("ffmpeg")
    if system_path:
        return system_path
    raise RuntimeError(
        "ffmpeg is not installed. Place ffmpeg(+ffprobe) next to the Python "
        "interpreter, install system ffmpeg, or: pip install imageio-ffmpeg"
    )


# ── Whisper transcription (audio fallback) ───────────────────────────────────


def _check_yt_dlp() -> None:
    """Raise a clear error if yt-dlp is not installed / not runnable."""
    yt_dlp = _resolve_yt_dlp()
    result = subprocess.run(
        [yt_dlp, "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "yt-dlp is installed but failed to run. "
            "Reinstall with: pip install -U 'yt-dlp[default]'"
        )


def _download_audio(video_id: str, output_dir: str) -> str:
    """Download audio from a YouTube video using yt-dlp.

    Downloads as mono 16kHz MP3 at low bitrate to minimize file size
    (optimal for Whisper transcription).

    Returns the path to the downloaded .mp3 file.
    """
    _check_yt_dlp()
    yt_dlp = _resolve_yt_dlp()
    ffmpeg = _resolve_ffmpeg()
    output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")
    cmd = [
        yt_dlp,
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "32K",          # low bitrate — ~14 MB/hr, good for Whisper
        "--postprocessor-args", "ffmpeg:-ac 1 -ar 16000",  # mono, 16kHz
        "--ffmpeg-location", os.path.dirname(ffmpeg),
        "--no-playlist",
        "-o", output_template,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {video_id}:\n{result.stderr[-500:]}")

    for ext in ["mp3", "m4a", "wav", "opus", "webm"]:
        path = os.path.join(output_dir, f"{video_id}.{ext}")
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"Downloaded audio not found for video {video_id}")


def _split_audio_ffmpeg(
    input_path: str,
    output_dir: str,
    chunk_seconds: int = 600,
) -> list[str]:
    """Split an audio file into chunks of *chunk_seconds* using ffmpeg.

    Returns a sorted list of chunk file paths.
    """
    ffmpeg = _resolve_ffmpeg()
    base = os.path.splitext(os.path.basename(input_path))[0]
    pattern = os.path.join(output_dir, f"{base}_chunk_%03d.mp3")
    cmd = [
        ffmpeg, "-i", input_path,
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-c", "copy",
        pattern,
        "-y",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg split failed:\n{result.stderr[-500:]}")

    chunks = sorted(
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith(f"{base}_chunk_") and f.endswith(".mp3")
    )
    logger.info("Split into %d chunks (%ds each)", len(chunks), chunk_seconds)
    return chunks


def _transcribe_chunk(audio_path: str, openai_client: openai.OpenAI, language: str) -> list[dict]:
    """Send a single audio file to OpenAI Whisper and return segments with timestamps."""
    with open(audio_path, "rb") as f:
        result = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            language=language,
        )
    # verbose_json returns segments with start, end, text
    if hasattr(result, "segments") and result.segments:
        return [
            {"start": s.get("start", s.get("Start", 0.0)) if isinstance(s, dict) else getattr(s, "start", 0.0),
             "duration": ((s.get("end", 0.0) if isinstance(s, dict) else getattr(s, "end", 0.0))
                          - (s.get("start", 0.0) if isinstance(s, dict) else getattr(s, "start", 0.0))),
             "text": (s.get("text", "") if isinstance(s, dict) else getattr(s, "text", "")).strip()}
            for s in result.segments
        ]
    # Fallback: return whole text as one segment
    text = result.text if hasattr(result, "text") else str(result)
    return [{"start": 0.0, "duration": 0.0, "text": text}]


def transcribe_video(
    video_id: str,
    openai_client: openai.OpenAI,
    language: str = "zh",
) -> list[dict]:
    """Download a YouTube video's audio and transcribe it with Whisper.

    Automatically splits audio into 10-minute chunks if it exceeds the
    Whisper 24 MB file limit.

    Returns segments in the same ``[{start, duration, text}]`` format
    as youtube_transcript_api so they can be processed identically.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        logger.info("Downloading audio for video %s ...", video_id)
        audio_path = _download_audio(video_id, tmpdir)

        file_size = os.path.getsize(audio_path)
        logger.info("Audio downloaded: %.1f MB", file_size / 1024 / 1024)

        if file_size <= WHISPER_MAX_BYTES:
            logger.info("Transcribing with Whisper (language=%s) ...", language)
            return _transcribe_chunk(audio_path, openai_client, language)

        # File too large — split into 10-minute chunks
        logger.info("Audio exceeds 24 MB, splitting into 10-minute chunks...")
        chunks = _split_audio_ffmpeg(audio_path, tmpdir, chunk_seconds=600)

        all_segments: list[dict] = []
        offset = 0.0
        for i, chunk_path in enumerate(chunks):
            logger.info("Transcribing chunk %d/%d ...", i + 1, len(chunks))
            segs = _transcribe_chunk(chunk_path, openai_client, language)
            for seg in segs:
                seg["start"] += offset
            all_segments.extend(segs)
            offset += 600.0  # each chunk is 10 minutes

        return all_segments


# ── Core function ─────────────────────────────────────────────────────────────


def fetch_transcript(
    video_id: str,
    preferred_langs: list[str] | None = None,
) -> tuple[list, str]:
    """Fetch the transcript for a YouTube video.

    Parameters
    ----------
    video_id : str
        The 11-character YouTube video ID.
    preferred_langs : list[str] | None
        Language codes in preference order, e.g. ``["zh-Hans", "zh-Hant", "en"]``.
        Defaults to Chinese variants first, then English.

    Returns
    -------
    tuple[list, str]
        (segments, language_code_used)

    Raises
    ------
    Exception
        If no transcript is available for the video.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        raise ImportError(
            "youtube-transcript-api is not installed. "
            "Run: pip install youtube-transcript-api"
        )

    if preferred_langs is None:
        preferred_langs = ["zh-Hans", "zh-Hant", "zh", "zh-CN", "zh-TW", "en"]

    api = YouTubeTranscriptApi()

    # Try fetching with preferred languages
    try:
        segments = api.fetch(video_id, languages=preferred_langs)
        # Determine which language was actually used
        transcript_list = api.list(video_id)
        lang = "unknown"
        for t in transcript_list:
            if t.language_code in preferred_langs:
                lang = t.language_code
                break
        logger.info("Fetched transcript in '%s' for video %s (%d segments)",
                    lang, video_id, len(segments))
        return list(segments), lang
    except Exception:
        pass

    # Last resort: try listing all and fetch the first available
    try:
        transcript_list = api.list(video_id)
        for t in transcript_list:
            segments = api.fetch(video_id, languages=[t.language_code])
            logger.info("Fetched transcript (lang=%s) for video %s (%d segments)",
                        t.language_code, video_id, len(segments))
            return list(segments), t.language_code
    except Exception:
        pass

    raise RuntimeError(f"No transcript available for video {video_id}")


def transcript_to_documents(
    video_id: str,
    segments: list[dict],
    lang: str,
    video_title: str = "",
    max_tokens: int = CHUNK_MAX_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
) -> list[dict]:
    """Convert transcript segments into ChromaDB-ready documents.

    Each document has: ``id``, ``text``, ``metadata``.
    """
    paragraphs = _merge_transcript_segments(segments, gap_seconds=3.0)
    full_text = "\n\n".join(paragraphs)

    if not full_text.strip():
        logger.warning("Empty transcript for video %s", video_id)
        return []

    chunks = chunk_text(full_text, max_tokens=max_tokens, overlap=overlap)
    logger.info("Video %s: %d paragraphs → %d chunks", video_id, len(paragraphs), len(chunks))

    documents: list[dict] = []
    for i, chunk in enumerate(chunks):
        doc_id = f"yt_{video_id}_{i}" if len(chunks) > 1 else f"yt_{video_id}"
        documents.append({
            "id": doc_id,
            "text": chunk,
            "metadata": {
                "source": "youtube",
                "video_id": video_id,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "title": video_title[:200] if video_title else "",
                "language": lang,
                "type": "youtube_transcript",
                "chunk_index": i,
                "total_chunks": len(chunks),
            },
        })

    return documents


# ── Main entry point ──────────────────────────────────────────────────────────


def run_youtube_ingestion(
    urls: list[str],
    preferred_langs: list[str] | None = None,
    db_path: str = CHROMADB_PATH,
    collection_name: str = CHROMADB_COLLECTION,
    whisper_fallback: bool = True,
    whisper_lang: str = "zh",
) -> tuple[int, dict[str, str]]:
    """Fetch transcripts for all URLs and ingest into ChromaDB.

    For each video the pipeline is:
    1. Try to fetch existing subtitles via youtube_transcript_api.
    2. If no subtitles exist AND *whisper_fallback* is True, download the
       audio with yt-dlp and transcribe it with OpenAI Whisper.

    Returns (total new documents inserted, {video_id: full_transcript_text}).
    """
    # Resolve video IDs
    video_ids: list[str] = []
    for url in urls:
        vid = extract_video_id(url)
        if vid:
            video_ids.append(vid)
        else:
            logger.warning("Could not extract video ID from: %s", url)

    if not video_ids:
        logger.error("No valid YouTube URLs provided.")
        return 0, {}

    logger.info("Processing %d video(s)", len(video_ids))

    # Create OpenAI client once — reused for both embedding and Whisper
    openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

    all_documents: list[dict] = []
    transcript_texts: dict[str, str] = {}

    for video_id in tqdm(video_ids, desc="Processing videos"):
        segments: list[dict] | None = None
        lang = "unknown"

        # ── Step 1: Try subtitle/caption API ──
        try:
            segments, lang = fetch_transcript(video_id, preferred_langs)
            logger.info("Video %s: subtitles found (lang=%s)", video_id, lang)
        except Exception as exc:
            logger.warning(
                "Video %s: no subtitles available (%s)",
                video_id, type(exc).__name__,
            )

        # ── Step 2: Whisper fallback ──
        if segments is None:
            if not whisper_fallback:
                logger.error(
                    "Video %s: skipped (no subtitles, Whisper fallback disabled)",
                    video_id,
                )
                continue
            try:
                logger.info(
                    "Video %s: falling back to Whisper transcription (lang=%s) ...",
                    video_id, whisper_lang,
                )
                segments = transcribe_video(video_id, openai_client, language=whisper_lang)
                lang = f"whisper-{whisper_lang}"
            except Exception as exc:
                logger.error("Video %s: Whisper transcription failed: %s", video_id, exc)
                continue

        paragraphs = _merge_transcript_segments(segments, gap_seconds=3.0)
        transcript_texts[video_id] = "\n\n".join(paragraphs)

        docs = transcript_to_documents(
            video_id=video_id,
            segments=segments,
            lang=lang,
        )
        all_documents.extend(docs)
        logger.info("Video %s: %d documents prepared", video_id, len(docs))

    if not all_documents:
        logger.warning("No documents to ingest.")
        return 0, transcript_texts

    collection = _get_chromadb_collection(db_path, collection_name)

    inserted = ingest_to_chromadb(all_documents, collection, openai_client)
    logger.info("YouTube ingestion complete — %d new documents added. "
                "Total in collection: %d", inserted, collection.count())
    return inserted, transcript_texts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch YouTube transcripts and ingest into ChromaDB"
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        default=[],
        metavar="URL",
        help="One or more YouTube video URLs or video IDs",
    )
    parser.add_argument(
        "--url-file",
        type=str,
        default=None,
        metavar="FILE",
        help="Path to a text file with one YouTube URL per line",
    )
    parser.add_argument(
        "--lang",
        nargs="+",
        default=None,
        metavar="LANG",
        help="Preferred transcript language codes in order (e.g. zh-Hans en). "
             "Defaults to Chinese variants first, then English.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=CHROMADB_PATH,
        help="Path to ChromaDB persistent storage",
    )
    parser.add_argument(
        "--whisper-lang",
        type=str,
        default="zh",
        metavar="LANG",
        help="Language code for Whisper transcription when no subtitles exist "
             "(e.g. zh, en, ja). Default: zh",
    )
    parser.add_argument(
        "--no-whisper",
        action="store_true",
        help="Disable Whisper fallback — skip videos that have no subtitles",
    )
    args = parser.parse_args()

    urls: list[str] = list(args.urls)

    if args.url_file:
        try:
            with open(args.url_file, "r", encoding="utf-8") as f:
                file_urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            urls.extend(file_urls)
            logger.info("Loaded %d URLs from %s", len(file_urls), args.url_file)
        except FileNotFoundError:
            logger.error("URL file not found: %s", args.url_file)
            sys.exit(1)

    if not urls:
        parser.print_help()
        sys.exit(1)

    run_youtube_ingestion(
        urls=urls,
        preferred_langs=args.lang,
        db_path=args.db_path,
        whisper_fallback=not args.no_whisper,
        whisper_lang=args.whisper_lang,
    )
