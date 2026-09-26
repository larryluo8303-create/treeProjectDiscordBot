"""Public client-facing API routes — chat, FAQ, KB search, promos, lessons,
image analysis, digest, and lesson archive.

These endpoints do NOT require admin JWT auth. They are gated by
a required API key (CLIENT_API_KEY) and per-IP rate limiting.
Fail-closed: with CLIENT_API_ENABLED=true but no key, the router is not
mounted at all (see bot.api.server.create_app).
"""

import asyncio
import base64
import hmac
import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from bot.config import (
    CLIENT_API_ENABLED,
    CLIENT_API_KEY,
    CLIENT_API_DAILY_LIMIT,
    CLIENT_CHAT_HISTORY_PER_MSG_CHARS,
    CLIENT_CHAT_HISTORY_TOTAL_CHARS,
    CLIENT_RATE_LIMIT_PER_MINUTE,
    CLIENT_VISION_LIMIT_PER_MINUTE,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public"])

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter (per IP, per minute)
# ---------------------------------------------------------------------------
_request_log: dict[str, list[float]] = defaultdict(list)
_vision_request_log: dict[str, list[float]] = defaultdict(list)


_last_cleanup: float = 0.0


def _check_window(
    log: dict[str, list[float]],
    key: str,
    limit: int,
    window_seconds: int,
    detail: str,
) -> None:
    now = time.time()
    window = now - window_seconds
    log[key] = [t for t in log[key] if t > window]
    if len(log[key]) >= limit:
        raise HTTPException(status_code=429, detail=detail)
    log[key].append(now)


def _rate_limit(request: Request) -> None:
    """Raise 429 if caller exceeds CLIENT_RATE_LIMIT_PER_MINUTE."""
    global _last_cleanup
    ip = request.client.host if request.client else "unknown"
    _check_window(_request_log, ip, CLIENT_RATE_LIMIT_PER_MINUTE, 60,
                  "Rate limit exceeded. Try again in a minute.")
    # Periodic cleanup: evict stale IPs every 5 minutes to prevent memory leak
    now = time.time()
    if now - _last_cleanup > 300:
        _last_cleanup = now
        window = now - 60
        for log in (_request_log, _vision_request_log):
            stale = [k for k, v in log.items() if not v or v[-1] < window]
            for k in stale:
                del log[k]


def _vision_rate_limit(request: Request) -> None:
    """Stricter per-IP limit for the expensive vision endpoint."""
    ip = request.client.host if request.client else "unknown"
    _check_window(_vision_request_log, ip, CLIENT_VISION_LIMIT_PER_MINUTE, 60,
                  "Vision rate limit exceeded. Try again in a minute.")


# ---------------------------------------------------------------------------
# Global daily budget for OpenAI-backed endpoints (all clients combined)
# ---------------------------------------------------------------------------
_daily_usage: dict[str, int] = {"day": "", "count": 0}
_daily_usage_lock = asyncio.Lock()


async def _check_daily_budget() -> None:
    """Raise 429 once the shared daily OpenAI budget is exhausted."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    async with _daily_usage_lock:
        if _daily_usage["day"] != today:
            _daily_usage["day"] = today
            _daily_usage["count"] = 0
        if _daily_usage["count"] >= CLIENT_API_DAILY_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Daily public API budget exhausted. Try again tomorrow.",
            )
        _daily_usage["count"] += 1


async def _spend_budget() -> None:
    """Dependency: enforce the shared daily budget on expensive endpoints."""
    await _check_daily_budget()


# ---------------------------------------------------------------------------
# API key dependency (fail-closed — an empty CLIENT_API_KEY denies access)
# ---------------------------------------------------------------------------
def _check_api_key(request: Request) -> None:
    """Validate the x-api-key header.

    Fail-closed: with no key configured the endpoints deny every request
    (503) instead of falling back to open access. Normally the router is
    not even mounted without a key (see bot.api.server.create_app); this
    is defense-in-depth for direct router use.
    """
    if not CLIENT_API_ENABLED:
        raise HTTPException(status_code=404, detail="Client API is disabled.")
    if not CLIENT_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Client API key is not configured (fail-closed).",
        )
    key = request.headers.get("x-api-key", "")
    # Constant-time comparison — never leak key validity via timing.
    if not hmac.compare_digest(key, CLIENT_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid API key.")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]


class ChatResponse(BaseModel):
    answer: str
    confidence: int
    sources: list[dict]


def build_history_str(conversation_history: list[dict] | None) -> str:
    """Flatten conversation history into a prompt string with hard caps.

    Per-message and total character limits prevent token-bombing the LLM
    with a huge history payload from an untrusted client.
    """
    if not conversation_history:
        return ""
    lines = []
    total = 0
    for msg in conversation_history[-10:]:  # limit to last 10 turns
        content = str(msg.get("content", ""))[:CLIENT_CHAT_HISTORY_PER_MSG_CHARS]
        role = "用户" if msg.get("role") == "user" else "助手"
        line = f"{role}: {content}"
        if total + len(line) > CLIENT_CHAT_HISTORY_TOTAL_CHARS:
            break
        total += len(line)
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    _key: None = Depends(_check_api_key),
    _rl: None = Depends(_rate_limit),
    _budget: None = Depends(_spend_budget),
) -> ChatResponse:
    """Ask the bot a question and get a RAG-powered answer."""
    from bot.api.server import get_collection, get_openai_client
    from bot.rag import run_rag_pipeline

    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if len(body.message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long (max 2000 chars).")

    collection = get_collection()
    openai_client = get_openai_client()
    if not collection or not openai_client:
        raise HTTPException(status_code=503, detail="Bot backend is not ready.")

    # Build conversation history string — capped per message and in total
    # to prevent token-bombing the LLM with a huge history payload.
    history_str = build_history_str(body.conversation_history)

    answer, confidence, context_chunks = await run_rag_pipeline(
        question=body.message.strip(),
        collection=collection,
        openai_client=openai_client,
        conversation_history=history_str,
    )

    # Record in bot stats
    try:
        from bot.stats import bot_stats
        bot_stats.record_query(
            question=body.message.strip(),
            channel_id=0,
            confidence=confidence,
            action="client_auto" if confidence >= 7 else "client_low",
            latency_ms=0,
        )
    except Exception:
        pass

    sources = []
    for chunk in context_chunks[:5]:
        sources.append({
            "text": chunk.get("text", "")[:300],
            "score": round(chunk.get("score", 0), 3),
            "type": chunk.get("metadata", {}).get("type", ""),
        })

    return ChatResponse(answer=answer, confidence=confidence, sources=sources)


# ---------------------------------------------------------------------------
# FAQ (public)
# ---------------------------------------------------------------------------
@router.get("/faq")
async def get_faq(
    request: Request,
    _key: None = Depends(_check_api_key),
) -> dict:
    """Return cached FAQ items."""
    from bot.faq import get_cached_faq
    raw = get_cached_faq()
    items = [{"question": it.get("q", ""), "answer": it.get("a", "")} for it in raw]
    return {"count": len(items), "items": items}


# ---------------------------------------------------------------------------
# KB Search (public)
# ---------------------------------------------------------------------------
@router.get("/kb/search")
async def search_kb(
    q: str,
    top_k: int = 5,
    request: Request = None,
    _key: None = Depends(_check_api_key),
    _rl: None = Depends(_rate_limit),
    _budget: None = Depends(_spend_budget),
) -> dict:
    """Semantic search the knowledge base."""
    from bot.api.server import get_collection, get_openai_client
    from bot.rag import retrieve_context

    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if top_k < 1 or top_k > 20:
        top_k = 5

    collection = get_collection()
    openai_client = get_openai_client()
    if not collection or not openai_client:
        raise HTTPException(status_code=503, detail="Bot backend is not ready.")

    results = await retrieve_context(q.strip(), collection, openai_client, top_k=top_k)
    return {
        "query": q.strip(),
        "count": len(results),
        "results": [
            {
                "text": r["text"][:500],
                "score": round(r.get("score", 0), 3),
                "type": r.get("metadata", {}).get("type", ""),
            }
            for r in results
        ],
    }


# ---------------------------------------------------------------------------
# Promos (public — upcoming only)
# ---------------------------------------------------------------------------
@router.get("/promos")
async def get_promos(
    request: Request,
    _key: None = Depends(_check_api_key),
) -> dict:
    """Return upcoming (not yet posted) promotions."""
    from bot.scheduler import list_promos

    promos = list_promos()
    upcoming = [p for p in promos if not p.get("posted") and p.get("scheduled_at", "") > ""]
    return {"count": len(upcoming), "items": upcoming}


# ---------------------------------------------------------------------------
# Lessons (public — upcoming only)
# ---------------------------------------------------------------------------
@router.get("/lessons")
async def get_lessons(
    request: Request,
    _key: None = Depends(_check_api_key),
) -> dict:
    """Return upcoming (not yet posted) lessons."""
    from bot.scheduler import list_lessons

    lessons = list_lessons()
    upcoming = [ls for ls in lessons if not ls.get("last_posted")]
    return {"count": len(upcoming), "items": upcoming}


# ---------------------------------------------------------------------------
# Image / Chart Analysis (Vision)
# ---------------------------------------------------------------------------
@router.post("/analyze-image")
async def analyze_image_endpoint(
    request: Request,
    image: UploadFile = File(...),
    text: str = "",
    _key: None = Depends(_check_api_key),
    _rl: None = Depends(_rate_limit),
    _vision_rl: None = Depends(_vision_rate_limit),
    _budget: None = Depends(_spend_budget),
) -> dict:
    """Upload an image (chart/screenshot) for GPT-4o vision analysis."""
    from bot.api.server import get_collection, get_openai_client
    from bot.rag import analyze_image, retrieve_context

    # Validate file type first (before checking backend readiness)
    content_type = image.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    # Read and validate size
    img_bytes = await image.read()
    if len(img_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Image too large (max 10MB).")

    openai_client = get_openai_client()
    collection = get_collection()
    if not openai_client:
        raise HTTPException(status_code=503, detail="Bot backend is not ready.")

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    data_url = f"data:{content_type};base64,{b64}"

    # Optionally retrieve RAG context for chart comparison
    context_chunks = []
    if text.strip() and collection:
        try:
            context_chunks = await retrieve_context(
                text.strip(), collection, openai_client, top_k=5
            )
        except Exception:
            pass

    answer, confidence = await analyze_image(
        image_urls=[data_url],
        user_text=text.strip(),
        openai_client=openai_client,
        context_chunks=context_chunks,
    )

    return {"answer": answer, "confidence": confidence}


# ---------------------------------------------------------------------------
# Public Daily Digest
# ---------------------------------------------------------------------------
@router.get("/digest")
async def get_digest(
    request: Request,
    _key: None = Depends(_check_api_key),
) -> dict:
    """Return a public-safe daily activity summary."""
    from bot.stats import bot_stats

    recent_24h = [
        r for r in bot_stats.recent
        if r.timestamp > time.time() - 86400
    ]

    total = len(recent_24h)
    auto = sum(1 for r in recent_24h if r.action == "auto_reply")
    avg_conf = (
        round(sum(r.confidence for r in recent_24h) / total, 1)
        if total else 0
    )

    # Top questions (deduplicated by first 60 chars)
    seen: set[str] = set()
    top_questions: list[str] = []
    for r in sorted(recent_24h, key=lambda x: x.confidence, reverse=True):
        key = r.question[:60].lower()
        if key not in seen:
            seen.add(key)
            top_questions.append(r.question)
        if len(top_questions) >= 10:
            break

    return {
        "period": "24h",
        "total_queries": total,
        "auto_replies": auto,
        "avg_confidence": avg_conf,
        "top_questions": top_questions,
        "generated_at": time.time(),
    }


# ---------------------------------------------------------------------------
# Lesson Archive (past lessons)
# ---------------------------------------------------------------------------
@router.get("/lessons/archive")
async def get_lesson_archive(
    request: Request,
    _key: None = Depends(_check_api_key),
) -> dict:
    """Return past (already posted) lessons."""
    from bot.scheduler import list_lessons

    lessons = list_lessons()
    posted = [ls for ls in lessons if ls.get("last_posted")]
    # Sort by scheduled_at descending (newest first)
    posted.sort(key=lambda x: x.get("scheduled_at", ""), reverse=True)
    return {"count": len(posted), "items": posted}


# ---------------------------------------------------------------------------
# Jin10 Market Flash News (public)
# ---------------------------------------------------------------------------
_news_cache: dict = {"items": [], "fetched_at": 0.0}
_NEWS_CACHE_TTL = 15  # seconds
_news_cache_lock = asyncio.Lock()


@router.get("/news")
async def get_news(
    request: Request,
    limit: int = 50,
    _key: None = Depends(_check_api_key),
    _rl: None = Depends(_rate_limit),
) -> dict:
    """Return recent important market flash news from Jin10."""
    import aiohttp

    from bot.news_feed import (
        JIN10_API_URL,
        JIN10_HEADERS,
        JIN10_PARAMS,
        _extract_items,
        extract_title_and_content,
    )

    # Fast path: serve from cache without acquiring the lock
    now = time.time()
    if now - _news_cache["fetched_at"] < _NEWS_CACHE_TTL and _news_cache["items"]:
        items = _news_cache["items"]
    else:
        async with _news_cache_lock:
            # Re-check after acquiring lock (another coroutine may have refreshed)
            now = time.time()
            if now - _news_cache["fetched_at"] < _NEWS_CACHE_TTL and _news_cache["items"]:
                items = _news_cache["items"]
            else:
                try:
                    async with aiohttp.ClientSession(
                        headers=JIN10_HEADERS,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as session:
                        async with session.get(JIN10_API_URL, params=JIN10_PARAMS) as resp:
                            if resp.status != 200:
                                raise HTTPException(
                                    status_code=502,
                                    detail=f"Jin10 API returned {resp.status}",
                                )
                            payload = await resp.json(content_type=None)

                    raw_items = _extract_items(payload)
                    items = []
                    for item in raw_items:
                        extras = item.get("extras") or {}
                        if extras.get("ad"):
                            continue
                        if item.get("type") == 1:
                            continue
                        data = item.get("data") or {}
                        raw_content = data.get("content", "")
                        if not raw_content.strip():
                            continue
                        title, body = extract_title_and_content(raw_content)
                        pic = data.get("pic", "")
                        link = data.get("link", "")
                        items.append({
                            "id": item.get("id", ""),
                            "time": item.get("time", ""),
                            "important": bool(item.get("important")),
                            "title": title,
                            "body": body,
                            "pic": pic if pic and pic.startswith("http") else None,
                            "link": link if link and link.startswith("http") else None,
                        })

                    _news_cache["items"] = items
                    _news_cache["fetched_at"] = now
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.warning("Failed to fetch Jin10 news: %s", exc)
                    if _news_cache["items"]:
                        items = _news_cache["items"]
                    else:
                        raise HTTPException(status_code=502, detail="Failed to fetch news")

    if limit < 1 or limit > 200:
        limit = 50
    items = items[:limit]
    return {"count": len(items), "items": items}


# ---------------------------------------------------------------------------
# Summaries (daily & weekly)
# ---------------------------------------------------------------------------
@router.get("/summaries")
async def get_summaries(
    request: Request,
    limit: int = 30,
    type: str | None = None,
    _key: None = Depends(_check_api_key),
) -> dict:
    """Return recent GPT-generated summaries (daily/weekly)."""
    from bot.utils import load_summaries

    if limit < 1 or limit > 100:
        limit = 30
    valid_types = {"daily", "weekly"}
    summary_type = type if type in valid_types else None
    items = load_summaries(limit=limit, summary_type=summary_type)
    return {"count": len(items), "items": items}
