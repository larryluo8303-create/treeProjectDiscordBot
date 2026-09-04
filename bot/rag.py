"""RAG pipeline: embed query → retrieve from ChromaDB → generate styled answer."""

import logging
import os
import re
import time
from pathlib import Path

import chromadb
import openai

from bot.cache import embedding_cache
from bot.utils import data_path as _data_path
from bot.config import (
    DEFAULT_STYLE_GUIDELINES,
    EMBEDDING_MODEL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    RAG_MAX_DISTANCE,
    RAG_TOP_K,
    SYSTEM_PROMPT_TEMPLATE,
    USER_PROMPT_TEMPLATE,
    VISION_MODEL,
    get_locale,
)

logger = logging.getLogger(__name__)

# Try to load custom style guidelines from file
_STYLE_PROFILE_PATH = Path(_data_path("data/style_profile.txt"))

# Cache for style guidelines to avoid re-reading disk on every query.
_style_cache: str | None = None
_style_cache_time: float = 0.0
_STYLE_CACHE_TTL: float = float(os.getenv("STYLE_CACHE_TTL", "300"))  # seconds


def _load_style_guidelines() -> str:
    """Load style guidelines from the profile file, or fall back to defaults.

    Results are cached for ``_STYLE_CACHE_TTL`` seconds.
    """
    global _style_cache, _style_cache_time
    now = time.monotonic()
    if _style_cache is not None and (now - _style_cache_time) < _STYLE_CACHE_TTL:
        return _style_cache

    if _STYLE_PROFILE_PATH.exists():
        text = _STYLE_PROFILE_PATH.read_text(encoding="utf-8")
        if text.strip():
            _style_cache = text
            _style_cache_time = now
            return text

    _style_cache = DEFAULT_STYLE_GUIDELINES
    _style_cache_time = now
    return DEFAULT_STYLE_GUIDELINES


# ── Negative feedback guidance ────────────────────────────────────────────────


_negative_cache: str | None = None
_negative_cache_time: float = 0.0
_NEGATIVE_CACHE_TTL: float = 120.0  # 2 minutes


def _build_negative_guidance() -> str:
    """Build a prompt section from rejected answers so the LLM avoids similar mistakes.

    Results are cached for ``_NEGATIVE_CACHE_TTL`` seconds.
    """
    global _negative_cache, _negative_cache_time
    now = time.monotonic()
    if _negative_cache is not None and (now - _negative_cache_time) < _NEGATIVE_CACHE_TTL:
        return _negative_cache

    from bot.review import load_negative_samples

    samples = load_negative_samples()
    if not samples:
        _negative_cache = ""
        _negative_cache_time = now
        return ""
    # Include last 5 negative examples to keep prompt size manageable
    recent = samples[-5:]
    lines = ["【以下是被频道主拒绝的回答示例，请避免类似的回答方式：】"]
    for s in recent:
        lines.append(f"问题：{s.get('question', '')[:200]}")
        lines.append(f"被拒绝的回答：{s.get('bad_answer', '')[:200]}")
        lines.append("---")
    _negative_cache = "\n".join(lines)
    _negative_cache_time = now
    return _negative_cache


# ── Retrieval ────────────────────────────────────────────────────────────────


async def retrieve_context(
    question: str,
    collection: chromadb.Collection,
    openai_client: openai.AsyncOpenAI,
    top_k: int = RAG_TOP_K,
    max_distance: float = RAG_MAX_DISTANCE,
) -> list[dict]:
    """Retrieve top-K relevant historical posts for a question.

    Returns list of ``{text, score, metadata}`` sorted by relevance (best first).
    """
    # Embed the question (with LRU cache)
    question_embedding = embedding_cache.get(question)
    if question_embedding is None:
        try:
            response = await openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[question],
            )
        except (openai.APITimeoutError, openai.APIConnectionError) as first_err:
            logger.warning("Embedding API error (%s) in retrieve_context — retrying once",
                           type(first_err).__name__)
            response = await openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[question],
            )
        question_embedding = response.data[0].embedding
        embedding_cache.put(question, question_embedding)

    # Query ChromaDB (async wrapper delegates to thread)
    results = await collection.query(
        query_embeddings=[question_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    if not results["documents"] or not results["documents"][0]:
        logger.info("No results found for query: %s", question[:100])
        return []

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    # Filter by max distance and deduplicate
    context_items: list[dict] = []
    seen_texts: set[str] = set()

    for doc, meta, dist in zip(documents, metadatas, distances):
        if dist > max_distance:
            continue
        # Dedup key: combine head + tail so messages that share a common opener
        # (e.g. "做ES主要看...") but diverge later are NOT collapsed, while truly
        # near-identical messages still are.
        normalized = doc.strip().lower()
        doc_key = normalized[:200] + "||" + normalized[-80:]
        if doc_key in seen_texts:
            continue
        seen_texts.add(doc_key)

        context_items.append({
            "text": doc,
            "score": 1.0 - dist,  # convert distance to similarity
            "distance": dist,
            "metadata": meta or {},
        })

    logger.info(
        "Retrieved %d context items (filtered from %d) for query: %s",
        len(context_items),
        len(documents),
        question[:80],
    )
    return context_items


# ── Generation ───────────────────────────────────────────────────────────────


def _build_context_block(context_chunks: list[dict]) -> str:
    """Format retrieved chunks into the context block for the prompt."""
    blocks: list[str] = []
    for i, chunk in enumerate(context_chunks, 1):
        meta = chunk.get("metadata", {})
        doc_type = meta.get("type", "")
        text = chunk["text"]

        if doc_type == "qa_pair":
            blocks.append(f"[Example {i} — Q&A]\n{text}")
        else:
            blocks.append(f"[Example {i}]\n{text}")

    return "\n\n---\n\n".join(blocks)


def _parse_confidence(text: str) -> tuple[str, int]:
    """Extract the CONFIDENCE: X line and return (clean_answer, score).

    If parsing fails, returns the full text and a default low score.
    """
    match = re.search(r"CONFIDENCE:\s*(\d+)", text, re.IGNORECASE)
    if match:
        score = int(match.group(1))
        score = max(1, min(10, score))
        # Remove the confidence line from the answer
        answer = text[: match.start()].rstrip("\n ")
        return answer, score
    return text.strip(), 3  # default low confidence if parsing fails


# ── Price-level redaction (safety net) ───────────────────────────────────────
#
# Even with prompt rules, the LLM occasionally leaks specific price numbers.
# These regexes catch the most common phrasings and rewrite them with relative
# language. Indicator parameters (EMA13, MA200, RSI 70), timeframes (5min, 1h),
# and percentages (90% 仓位) are intentionally left untouched.

_NUM = r"\d+(?:\.\d+)?"  # integer or decimal
_RANGE = rf"{_NUM}(?:\s*[-~～到至–—]\s*{_NUM})?"  # number or range

_PRICE_REDACTIONS: list[tuple[re.Pattern, str]] = [
    # 2+ digit number directly followed by 附近/一带/位置/区域 — most common phrasing for a price level.
    # Catches "86附近", "之前提到的 86 附近", "3900 一带" etc.
    # Negative lookbehind on letters/digits prevents matching numbers embedded in identifiers like EMA13/MA200.
    (re.compile(r"(?<![A-Za-z\d])\d{2,}(?:\.\d+)?\s*(?:附近|一带|位置|区域)"), "关键位附近"),
    # 支撑/阻力/压力 + (位/区/区域)? + (在|于)? + 数字 + (附近|一带|位置|区域)?
    (re.compile(rf"(支撑|阻力|压力)(?:位|区|区域)?\s*(?:在|于)?\s*{_RANGE}(?:\s*(?:附近|一带|位置|区域))?"), r"\1附近"),
    # 目标 (价/位)? + 数字
    (re.compile(rf"目标(?:价|位)?\s*(?:在|于|看)?\s*{_RANGE}(?:\s*(?:附近|一带|位置|区域))?"), "目标位"),
    # 止损 (位)? + 数字
    (re.compile(rf"止损(?:位)?\s*(?:在|于|设|放)?\s*{_RANGE}(?:\s*(?:附近|一带|位置|区域))?"), "止损位"),
    # 突破/跌破/站上/站稳/失守/回踩 + 数字
    (re.compile(rf"(突破|跌破|站上|站稳|失守|回踩)\s*{_RANGE}(?:\s*(?:附近|一带|位置|区域))?"), r"\1关键位"),
    # 进场/入场/出场/买入/卖出/进多/进空/加仓/减仓/加过/减过 + 数字
    (re.compile(rf"(进场|入场|出场|买入|卖出|进多|进空|加仓|减仓|加过|减过)\s*(?:在|于)?\s*{_RANGE}(?:\s*(?:附近|一带|位置|区域))?"), r"\1"),
    # 区间 + 范围  →  对应区间 (must run before generic range below)
    (re.compile(rf"区间\s*\d{{2,}}(?:\.\d+)?\s*[-~～到至–—]\s*\d{{2,}}(?:\.\d+)?"), "对应区间"),
    # Bare prepositional reference: 在/到/至/看/破/过/于 + 2+digit number (lookbehind skips identifiers)
    (re.compile(r"(在|到|至|看|破|过|于)\s*(?<![A-Za-z\d])\d{2,}(?:\.\d+)?"), r"\1关键位"),
    # 数字 + 点位/位/点 (3+ digits to avoid "13点" time reference)
    (re.compile(r"(?<![A-Za-z\d])\d{3,}(?:\.\d+)?\s*(?:点位|点|位)"), "对应位置"),
    # Standalone numeric range with 2+ digit endpoints
    (re.compile(r"(?<![A-Za-z\d])\d{2,}(?:\.\d+)?\s*[-~～到至–—]\s*\d{2,}(?:\.\d+)?(?![A-Za-z])"), "对应区间"),
]

# Cosmetic cleanup: collapse adjacent duplicate position words after redaction
_DEDUP_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(附近|一带|位置|区域|区间|关键位|目标位|止损位)\s*\1"), r"\1"),
    # "关键位附近 附近" → "关键位附近"
    (re.compile(r"关键位附近\s*(?:附近|一带)"), "关键位附近"),
    # "关键位 附近" → "关键位附近"
    (re.compile(r"关键位\s+(?:附近|一带)"), "关键位附近"),
    (re.compile(r" {2,}"), " "),
]


def _redact_price_levels(text: str) -> tuple[str, int]:
    """Strip specific price numbers from text. Returns (clean_text, hits)."""
    hits = 0
    for pattern, replacement in _PRICE_REDACTIONS:
        text, n = pattern.subn(replacement, text)
        hits += n
    if hits:
        for pattern, replacement in _DEDUP_PATTERNS:
            text = pattern.sub(replacement, text)
    return text, hits


def _record_openai_call(success: bool) -> None:
    """Record one logical OpenAI request (not each retry attempt)."""
    try:
        from bot.reliability import record_openai_call
        record_openai_call(success)
    except Exception:
        pass


async def _openai_chat_with_retry(
    openai_client: openai.AsyncOpenAI,
    *,
    model: str,
    messages: list[dict],
    max_tokens: int = LLM_MAX_TOKENS,
    temperature: float = LLM_TEMPERATURE,
) -> str | None:
    """Call OpenAI chat completions with a single retry on transient errors.

    Returns the raw response text, or ``None`` if both attempts fail.
    Records SLA success/failure once per logical request, so a recovered
    retry does not inflate the error rate.
    """
    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        _record_openai_call(True)
        return response.choices[0].message.content or ""
    except (openai.APITimeoutError, openai.APIConnectionError) as first_err:
        logger.warning("OpenAI API error (%s) — retrying once", type(first_err).__name__)
        try:
            response = await openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            _record_openai_call(True)
            return response.choices[0].message.content or ""
        except Exception as retry_err:
            _record_openai_call(False)
            logger.error("OpenAI API retry also failed: %s", retry_err)
            return None


async def generate_answer(
    question: str,
    context_chunks: list[dict],
    openai_client: openai.AsyncOpenAI,
    conversation_history: str = "",
) -> tuple[str, int]:
    """Generate an answer using retrieved context.

    Returns
    -------
    tuple[str, int]
        (answer_text, confidence_score)
    """
    style_guidelines = _load_style_guidelines()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(style_guidelines=style_guidelines)

    # Inject negative samples (rejected answers) into the system prompt
    negative_guidance = _build_negative_guidance()
    if negative_guidance:
        system_prompt += "\n\n" + negative_guidance

    context_block = _build_context_block(context_chunks)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        context=context_block,
        conversation_history=conversation_history,
        question=question,
    )

    raw_answer = await _openai_chat_with_retry(
        openai_client,
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    if raw_answer is None:
        return get_locale("no_answer"), 1

    answer, confidence = _parse_confidence(raw_answer)
    answer, redactions = _redact_price_levels(answer)
    if redactions:
        logger.info("Redacted %d price-level mention(s) from answer", redactions)
    logger.info("Generated answer (confidence=%d, len=%d chars)", confidence, len(answer))
    return answer, confidence


# ── Full pipeline ────────────────────────────────────────────────────────────


async def run_rag_pipeline(
    question: str,
    collection: chromadb.Collection,
    openai_client: openai.AsyncOpenAI,
    conversation_history: str = "",
) -> tuple[str, int, list[dict]]:
    """Run the full RAG pipeline: retrieve → generate.

    Returns
    -------
    tuple[str, int, list[dict]]
        (answer_text, confidence_score, context_chunks)
    """
    context_chunks = await retrieve_context(question, collection, openai_client)

    if not context_chunks:
        return (
            "这个我不太确定，等频道主来回答",
            1,
            [],
        )

    answer, confidence = await generate_answer(
        question, context_chunks, openai_client, conversation_history
    )
    return answer, confidence, context_chunks


# ── Vision (image analysis) ──────────────────────────────────────────────────

VISION_SYSTEM_PROMPT = """你是一个专业的股票技术分析AI助手。用户会发送K线图、技术指标截图或其他股市相关图表。

你的任务：
1. 仔细分析图片中的技术形态（如分型、笔、线段、中枢、趋势线、均线、MACD、RSI等）。
2. 识别关键价格水平（支撑位、阻力位）。
3. 判断当前趋势方向和可能的买卖信号。
4. 用简体中文、简洁直接的语气回答，就像一个资深交易员在Discord里分析盘面。

{style_guidelines}

注意：
- 回复要简洁，1-5句话即可，不需要长篇大论。
- 如果图片不清楚或不是股票相关图表，简短说明。
- 不要添加"以上不构成投资建议"等免责声明。
- 【做分析，不提点位】详细说明图中的趋势、形态、指标信号、可能的交易逻辑——这部分要详细。但不得引用图上任何具体价格数字、点位区间或目标价。用相对描述代替数字：
  - "支撑在 3900" → "前期低点支撑区域 / 均线附近"
  - "压力 250" → "前期高点压力 / 上方压力区"
  - "突破 18000" → "突破前期高点 / 突破关键压力"
  - "止损 3850" → "跌破关键位止损"
  指标参数（EMA13/RSI/MA200）、时间周期（5min/1h/4h/日线）、仓位百分比可以提，仅禁价格本身的数字。被问具体点位时回复 "具体点位需要根据当前实时行情判断，我只能分享分析方法和思路"。

在回复的最后，另起一行，严格输出：
CONFIDENCE: X
其中X是1到10的数字，表示你对图片分析的信心。"""


async def analyze_image(
    image_urls: list[str],
    user_text: str,
    openai_client: openai.AsyncOpenAI,
    conversation_history: str = "",
    context_chunks: list[dict] | None = None,
) -> tuple[str, int]:
    """Analyze image(s) using GPT-4o vision.

    Parameters
    ----------
    image_urls : list[str]
        URLs of the images to analyze.
    user_text : str
        Optional text message from the user accompanying the image.
    openai_client : openai.AsyncOpenAI
    conversation_history : str
        Recent conversation context.
    context_chunks : list[dict] | None
        Optional RAG context from knowledge base for chart comparison.

    Returns
    -------
    tuple[str, int]
        (answer_text, confidence_score)
    """
    style_guidelines = _load_style_guidelines()
    system_prompt = VISION_SYSTEM_PROMPT.format(style_guidelines=style_guidelines)

    # Build user message content with images
    user_content: list[dict] = []

    for url in image_urls:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "high"},
        })

    # Build text prompt
    text_parts = []
    if conversation_history:
        text_parts.append(conversation_history)

    # Inject RAG context for chart comparison when available
    if context_chunks:
        context_block = _build_context_block(context_chunks)
        text_parts.append(
            "以下是频道主过往关于类似标的/形态的历史分析，供参考对比：\n" + context_block
        )

    if user_text:
        text_parts.append(f"用户提问: {user_text}")
    else:
        text_parts.append("请分析这张图片，给出技术分析观点。")

    user_content.append({"type": "text", "text": "\n".join(text_parts)})

    raw_answer = await _openai_chat_with_retry(
        openai_client,
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    if raw_answer is None:
        return "抱歉，图片分析失败，请稍后再试。", 1

    answer, confidence = _parse_confidence(raw_answer)
    answer, redactions = _redact_price_levels(answer)
    if redactions:
        logger.info("Redacted %d price-level mention(s) from vision answer", redactions)
    logger.info("Vision analysis complete (confidence=%d, len=%d chars)", confidence, len(answer))
    return answer, confidence
