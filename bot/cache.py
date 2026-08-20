"""LRU embedding cache with optional semantic deduplication.

Caches OpenAI embedding results keyed by question text hash to avoid
redundant API calls for identical (or near-identical) questions.
"""

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MAX_SIZE = 256
_DEFAULT_TTL = 600.0  # 10 minutes


class EmbeddingCache:
    """In-memory LRU cache for embedding vectors."""

    def __init__(self, max_size: int = _DEFAULT_MAX_SIZE, ttl: float = _DEFAULT_TTL) -> None:
        self._cache: OrderedDict[str, tuple[float, list[float]]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl
        self.hits: int = 0
        self.misses: int = 0

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()

    def get(self, text: str) -> list[float] | None:
        """Return cached embedding or None."""
        key = self._key(text)
        entry = self._cache.get(key)
        if entry is None:
            self.misses += 1
            return None
        ts, embedding = entry
        if time.monotonic() - ts > self._ttl:
            # Expired
            del self._cache[key]
            self.misses += 1
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self.hits += 1
        return embedding

    def put(self, text: str, embedding: list[float]) -> None:
        """Store an embedding in the cache."""
        key = self._key(text)
        self._cache[key] = (time.monotonic(), embedding)
        self._cache.move_to_end(key)
        # Evict oldest if over capacity
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }


# Module-level singleton
embedding_cache = EmbeddingCache()
