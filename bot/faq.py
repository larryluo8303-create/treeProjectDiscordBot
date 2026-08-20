"""FAQ auto-generation from high-frequency, high-confidence Q&A pairs.

Analyses the recent query history from bot_stats and uses GPT to cluster
and summarize the most common questions into a clean FAQ list.
Persists to ``data/faq.json`` for caching.
"""

import json
import logging
import os
from datetime import datetime, timezone

import openai

from bot.config import LLM_MODEL
from bot.stats import bot_stats
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

FAQ_FILE = data_path(os.getenv("FAQ_FILE", "data/faq.json"))
FAQ_MIN_CONFIDENCE = int(os.getenv("FAQ_MIN_CONFIDENCE", "7"))
FAQ_MAX_ITEMS = int(os.getenv("FAQ_MAX_ITEMS", "10"))


def _load_faq() -> dict:
    try:
        with open(FAQ_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_faq(data: dict) -> None:
    atomic_json_write(FAQ_FILE, data, ensure_ascii=False, indent=2)


def get_cached_faq() -> list[dict]:
    """Return cached FAQ items, or empty list if none."""
    data = _load_faq()
    return data.get("items", [])


async def generate_faq(
    openai_client: openai.AsyncOpenAI,
    *,
    return_status: bool = False,
) -> list[dict] | tuple[list[dict], str]:
    """Analyze recent high-confidence queries and generate FAQ items via GPT.

    Returns a list of dicts: [{"q": "...", "a": "..."}]
    If *return_status* is True, returns (items, status_message).
    """
    def _result(items: list[dict], msg: str):
        return (items, msg) if return_status else items

    # Collect high-confidence auto-reply queries
    high_conf = [
        r for r in bot_stats.recent
        if r.confidence >= FAQ_MIN_CONFIDENCE and r.action == "auto_reply"
    ]

    if len(high_conf) < 3:
        logger.info("Not enough high-confidence queries for FAQ generation (%d)", len(high_conf))
        return _result(
            get_cached_faq(),
            f"Need at least 3 high-confidence auto-reply queries (currently {len(high_conf)}). "
            f"Total recent queries: {len(bot_stats.recent)}, threshold: confidence >= {FAQ_MIN_CONFIDENCE} & auto_reply.",
        )

    # Build a question list for GPT to cluster and summarize
    questions = [r.question for r in high_conf]
    # Deduplicate while preserving order
    seen = set()
    unique_qs = []
    for q in questions:
        key = q.strip().lower()
        if key not in seen:
            seen.add(key)
            unique_qs.append(q)

    # Limit to most recent 50 unique questions
    unique_qs = unique_qs[-50:]

    prompt = (
        "你是一个FAQ生成助手。以下是用户最近的高频提问列表。\n"
        "请将这些问题归类合并，生成最多{}个最有代表性的FAQ条目。\n"
        "每个条目包含一个简洁的问题和一个简短的回答。\n"
        "输出严格JSON数组格式: [{{\"q\": \"问题\", \"a\": \"简短回答\"}}]\n"
        "不要输出任何其他文字，只输出JSON数组。\n\n"
        "用户提问列表：\n{}"
    ).format(FAQ_MAX_ITEMS, "\n".join(f"- {q}" for q in unique_qs))

    try:
        response = await openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        raw = (response.choices[0].message.content or "").strip()

        # Extract JSON array from response
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            logger.warning("FAQ generation: no JSON array found in response")
            return get_cached_faq()

        items = json.loads(raw[start:end + 1])

        # Validate structure
        faq_items = []
        for item in items[:FAQ_MAX_ITEMS]:
            if isinstance(item, dict) and "q" in item and "a" in item:
                faq_items.append({"q": str(item["q"]), "a": str(item["a"])})

        if faq_items:
            _save_faq({
                "items": faq_items,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_count": len(unique_qs),
            })
            logger.info("FAQ generated: %d items from %d unique questions",
                        len(faq_items), len(unique_qs))

        return _result(faq_items, f"Generated {len(faq_items)} FAQ items from {len(unique_qs)} questions.")

    except Exception as exc:
        logger.warning("FAQ generation failed: %s", exc)
        return _result(get_cached_faq(), f"FAQ generation failed: {exc}")
