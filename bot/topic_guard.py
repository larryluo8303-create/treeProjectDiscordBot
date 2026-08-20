"""Topic guard — enforce on-topic discussion in restricted channels.

Certain channels can be restricted so that **only** trading / signal / stock /
investment-related discussion is allowed.  Off-topic chatter, nonsense,
offensive / toxic messages, and other unrelated content is auto-deleted.

Classification is done via a lightweight GPT-4o-mini call that returns a single
label: ``on_topic``, ``off_topic``, or ``offensive``.  Results are cached
briefly (per message hash) to avoid duplicate API calls.

The module is stateless aside from its OpenAI client reference and a small
in-memory LRU cache.
"""

import hashlib
import logging
import re
import time
from collections import OrderedDict

import openai as _openai_mod

from bot.config import LLM_MODEL, TOPIC_RESTRICTED_CHANNEL_IDS

logger = logging.getLogger(__name__)

# ── Module state ──────────────────────────────────────────────────────────

_openai_client: _openai_mod.AsyncOpenAI | None = None


def set_openai_client(client: _openai_mod.AsyncOpenAI) -> None:
    """Inject the shared OpenAI client."""
    global _openai_client
    _openai_client = client


# ── Classification cache (LRU with TTL) ───────────────────────────────────

_CACHE_MAX = 200
_CACHE_TTL = 300.0  # 5 minutes

# {content_hash: (timestamp, label)}
_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()


def _cache_key(content: str) -> str:
    return hashlib.sha256(content.strip().lower().encode("utf-8")).hexdigest()[:16]


def _cache_get(content: str) -> str | None:
    key = _cache_key(content)
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, label = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return label


def _cache_put(content: str, label: str) -> None:
    key = _cache_key(content)
    _cache[key] = (time.monotonic(), label)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


# ── Classification prompt ─────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a Discord channel moderator for a stock/forex/crypto trading community.

Your ONLY job is to classify a user message into exactly ONE category:
- "on_topic" — related to trading, signals, technical analysis, market discussion, stocks, forex, crypto, options, futures, investment strategies, economic news, chart analysis, entry/exit points, risk management, portfolio, earnings, or asking the channel host questions about any of these. Greetings directed at the host or community (like "老师好", "大家好") are also on_topic.
- "off_topic" — idle chatter, jokes, memes, personal life, food, weather, gaming, sports, or anything unrelated to trading/investing. Includes random emoji-only messages, "haha", gibberish, or meaningless short messages.
- "offensive" — insults, harassment, hate speech, threats, discrimination, sexual content, or toxic behavior.

Reply with ONLY the label: on_topic, off_topic, or offensive
Do NOT explain. Do NOT add any other text."""


def _is_trivial(content: str) -> str | None:
    """Quick pre-filter for obviously trivial messages without calling GPT.

    Returns a label if we can decide without GPT, else None.
    """
    text = content.strip()

    # Very short messages (1-2 chars) are likely off-topic noise
    if len(text) <= 2:
        return "off_topic"

    # Pure emoji (no text at all)
    # Strip all emoji, ZWJ sequences, variation selectors
    stripped = re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        r"\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F"
        r"\U0000200D\U00002600-\U000026FF\U00002700-\U000027BF"
        r"\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]+",
        "", text
    ).strip()
    if not stripped:
        return "off_topic"

    return None


# ── Public API ────────────────────────────────────────────────────────────

# Pre-compute set for O(1) lookup
_TOPIC_RESTRICTED_SET: set[int] = set(TOPIC_RESTRICTED_CHANNEL_IDS)


def is_topic_restricted(channel_id: int) -> bool:
    """Return True if the channel is topic-restricted."""
    return channel_id in _TOPIC_RESTRICTED_SET


async def classify_message(content: str) -> str:
    """Classify a message as on_topic / off_topic / offensive.

    Returns the label string.
    Falls back to "on_topic" (permissive) if GPT call fails.
    """
    if not content or not content.strip():
        return "off_topic"

    # Check trivial pre-filter
    trivial = _is_trivial(content)
    if trivial:
        return trivial

    # Check cache
    cached = _cache_get(content)
    if cached:
        return cached

    # GPT classification
    if _openai_client is None:
        logger.warning("Topic guard: no OpenAI client, defaulting to on_topic")
        return "on_topic"

    try:
        response = await _openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content[:500]},  # cap at 500 chars
            ],
            max_tokens=5,
            temperature=0.0,
        )
        raw = (response.choices[0].message.content or "").strip().lower()

        # Normalize to valid labels
        if "offensive" in raw:
            label = "offensive"
        elif "off_topic" in raw:
            label = "off_topic"
        else:
            label = "on_topic"

        _cache_put(content, label)
        logger.debug("Topic guard: classified %r → %s", content[:60], label)
        return label

    except Exception as exc:
        logger.warning("Topic guard: GPT call failed (%s), defaulting to on_topic", exc)
        return "on_topic"


async def check_topic(channel_id: int, content: str) -> str | None:
    """Check if a message violates topic restrictions.

    Returns a reason string if the message should be deleted, or None if OK.
    Only applies to channels in TOPIC_RESTRICTED_CHANNEL_IDS.
    """
    if not is_topic_restricted(channel_id):
        return None

    label = await classify_message(content)

    if label == "offensive":
        return "topic-restricted channel: offensive content"
    elif label == "off_topic":
        return "topic-restricted channel: off-topic (only trading/signal discussion allowed)"

    return None
