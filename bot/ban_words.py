"""Ban-words list — exact + semantic similarity matching.

Provides:
- Persistent ban-word list (``data/ban_words.json``).
- Exact substring matching (case-insensitive).
- Semantic similarity matching via OpenAI embeddings — catches messages whose
  *meaning* is close to a banned phrase even if the exact words differ.
- CRUD helpers used by slash commands (``/add_ban_word``, etc.).
- Pre-computed embedding cache that updates when the list changes.

The semantic check is **optional**: it only runs when an ``openai.AsyncOpenAI``
client is available (set via ``set_openai_client``).  Without it, only exact
substring matching is performed.
"""

import json
import logging
import math
import os
from typing import Any

import openai as _openai_mod

from bot.config import (
    AUTO_MOD_BAN_WORDS_FILE,
    AUTO_MOD_BAN_WORDS_SIMILARITY,
    EMBEDDING_MODEL,
)
from bot.utils import atomic_json_write

logger = logging.getLogger(__name__)

# ── Module state ──────────────────────────────────────────────────────────

_openai_client: _openai_mod.AsyncOpenAI | None = None

# Each entry: {"word": str, "embedding": list[float] | None}
_ban_entries: list[dict[str, Any]] = []
# Pre-computed lowercase set for O(1) exact substring checks
_exact_words: list[str] = []  # lowered, kept in sync with _ban_entries


def set_openai_client(client: _openai_mod.AsyncOpenAI) -> None:
    """Inject the shared OpenAI client for embedding computation."""
    global _openai_client
    _openai_client = client


# ── Persistence ───────────────────────────────────────────────────────────

def _load() -> list[dict[str, Any]]:
    try:
        with open(AUTO_MOD_BAN_WORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict[str, Any]]) -> None:
    atomic_json_write(AUTO_MOD_BAN_WORDS_FILE, entries, ensure_ascii=False, indent=2)


def _rebuild_exact() -> None:
    """Rebuild the fast-lookup list from current entries."""
    global _exact_words
    _exact_words = [e["word"].lower() for e in _ban_entries]


def load_ban_words() -> None:
    """Load the ban-word list from disk into memory."""
    global _ban_entries
    _ban_entries = _load()
    _rebuild_exact()
    logger.info("Ban words: loaded %d entries from %s", len(_ban_entries), AUTO_MOD_BAN_WORDS_FILE)


def get_ban_words() -> list[str]:
    """Return the current list of banned words/phrases."""
    return [e["word"] for e in _ban_entries]


# ── Embedding helpers ─────────────────────────────────────────────────────

async def _compute_embedding(text: str) -> list[float] | None:
    """Compute embedding for a text string. Returns None on failure."""
    if _openai_client is None:
        return None
    try:
        response = await _openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[text],
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.warning("Ban words: embedding failed for %r: %s", text[:50], exc)
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── CRUD ──────────────────────────────────────────────────────────────────

async def add_ban_word(word: str) -> bool:
    """Add a word/phrase to the ban list. Returns False if already exists."""
    word = word.strip()
    if not word:
        return False

    # Check for duplicates (case-insensitive)
    for e in _ban_entries:
        if e["word"].lower() == word.lower():
            return False

    embedding = await _compute_embedding(word)
    entry: dict[str, Any] = {"word": word, "embedding": embedding}
    _ban_entries.append(entry)
    _rebuild_exact()
    _save(_ban_entries)
    logger.info("Ban words: added %r (embedding=%s)", word, embedding is not None)
    return True


def remove_ban_word(word: str) -> bool:
    """Remove a word/phrase from the ban list. Returns False if not found."""
    global _ban_entries
    word_lower = word.strip().lower()
    original_len = len(_ban_entries)
    _ban_entries = [e for e in _ban_entries if e["word"].lower() != word_lower]
    if len(_ban_entries) < original_len:
        _rebuild_exact()
        _save(_ban_entries)
        logger.info("Ban words: removed %r", word)
        return True
    return False


async def refresh_embeddings() -> int:
    """Recompute embeddings for entries that are missing them. Returns count updated."""
    updated = 0
    for entry in _ban_entries:
        if entry.get("embedding") is None:
            emb = await _compute_embedding(entry["word"])
            if emb is not None:
                entry["embedding"] = emb
                updated += 1
    if updated:
        _save(_ban_entries)
    return updated


# ── Matching ──────────────────────────────────────────────────────────────

def check_exact(content: str) -> str | None:
    """Check if content contains any banned word (exact substring, case-insensitive).

    Returns the matched ban word, or None.
    """
    if not _exact_words:
        return None
    content_lower = content.lower()
    for i, word_lower in enumerate(_exact_words):
        if word_lower in content_lower:
            return _ban_entries[i]["word"]
    return None


async def check_semantic(content: str) -> tuple[str, float] | None:
    """Check if content is semantically similar to any banned word.

    Returns (matched_word, similarity_score) if above threshold, else None.
    Skips entries without embeddings.
    """
    if not _ban_entries or _openai_client is None:
        return None

    # Only check messages with enough substance
    if len(content.strip()) < 5:
        return None

    msg_embedding = await _compute_embedding(content)
    if msg_embedding is None:
        return None

    best_word: str | None = None
    best_score: float = 0.0

    for entry in _ban_entries:
        entry_emb = entry.get("embedding")
        if entry_emb is None:
            continue
        score = _cosine_similarity(msg_embedding, entry_emb)
        if score > best_score:
            best_score = score
            best_word = entry["word"]

    if best_word is not None and best_score >= AUTO_MOD_BAN_WORDS_SIMILARITY:
        return (best_word, best_score)

    return None
