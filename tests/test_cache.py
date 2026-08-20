"""Tests for bot.cache module (embedding LRU cache)."""

import time

from bot.cache import EmbeddingCache


class TestEmbeddingCache:
    def test_put_and_get(self):
        cache = EmbeddingCache(max_size=10, ttl=60)
        cache.put("hello", [0.1, 0.2, 0.3])
        result = cache.get("hello")
        assert result == [0.1, 0.2, 0.3]
        assert cache.hits == 1
        assert cache.misses == 0

    def test_miss(self):
        cache = EmbeddingCache(max_size=10, ttl=60)
        result = cache.get("nonexistent")
        assert result is None
        assert cache.misses == 1

    def test_case_insensitive_key(self):
        cache = EmbeddingCache(max_size=10, ttl=60)
        cache.put("Hello World", [1.0])
        result = cache.get("hello world")
        assert result == [1.0]

    def test_ttl_expiration(self):
        cache = EmbeddingCache(max_size=10, ttl=0.01)
        cache.put("test", [1.0])
        time.sleep(0.02)
        result = cache.get("test")
        assert result is None
        assert cache.misses == 1

    def test_lru_eviction(self):
        cache = EmbeddingCache(max_size=3, ttl=60)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])
        cache.put("d", [4.0])  # should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == [2.0]
        assert cache.get("d") == [4.0]

    def test_stats(self):
        cache = EmbeddingCache(max_size=10, ttl=60)
        cache.put("x", [1.0])
        cache.get("x")   # hit
        cache.get("y")   # miss
        s = cache.stats()
        assert s["size"] == 1
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["hit_rate"] == 0.5

    def test_overwrite_existing_key(self):
        cache = EmbeddingCache(max_size=10, ttl=60)
        cache.put("k", [1.0])
        cache.put("k", [2.0])
        assert cache.get("k") == [2.0]
        assert len(cache._cache) == 1
