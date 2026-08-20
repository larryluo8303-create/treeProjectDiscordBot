"""Tests for bot.faq module — FAQ persistence, caching, generation."""

import json
import os
import tempfile

import pytest

import bot.faq as faq_module


class TestFaqPersistence:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._file = os.path.join(self._tmpdir, "faq.json")
        self._orig = faq_module.FAQ_FILE
        faq_module.FAQ_FILE = self._file

    def teardown_method(self):
        faq_module.FAQ_FILE = self._orig
        for f in [self._file, self._file + ".tmp"]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(self._tmpdir):
            os.rmdir(self._tmpdir)

    def test_load_missing_returns_empty(self):
        assert faq_module._load_faq() == {}

    def test_load_corrupt_json(self):
        with open(self._file, "w") as f:
            f.write("{{broken json")
        assert faq_module._load_faq() == {}

    def test_save_and_load(self):
        data = {"items": [{"q": "What?", "a": "Something"}], "generated_at": "now"}
        faq_module._save_faq(data)
        loaded = faq_module._load_faq()
        assert loaded["items"][0]["q"] == "What?"

    def test_get_cached_faq_empty(self):
        assert faq_module.get_cached_faq() == []

    def test_get_cached_faq_with_data(self):
        data = {"items": [{"q": "Q1", "a": "A1"}, {"q": "Q2", "a": "A2"}]}
        faq_module._save_faq(data)
        result = faq_module.get_cached_faq()
        assert len(result) == 2
        assert result[0]["q"] == "Q1"

    def test_atomic_write_no_tmp_leftover(self):
        faq_module._save_faq({"items": []})
        assert os.path.exists(self._file)
        assert not os.path.exists(self._file + ".tmp")


class TestGenerateFaqNotEnoughData:
    """Test that generate_faq returns cache when not enough data."""

    @pytest.mark.asyncio
    async def test_returns_cache_when_too_few_queries(self):
        from unittest.mock import AsyncMock, MagicMock
        from collections import deque
        from bot.stats import BotStats, QueryRecord
        import time

        # Prepare stats with only 2 records (minimum is 3)
        stats = BotStats.__new__(BotStats)
        stats.total_queries = 2
        stats.auto_replies = 2
        stats.forwards = 0
        stats.total_confidence = 16
        stats.total_latency_ms = 200
        stats.channel_counts = {}
        stats._dirty = False
        stats._save_task = None
        now = time.time()
        stats.recent = deque([
            QueryRecord("q1?", 1, 8, "auto_reply", 100, now),
            QueryRecord("q2?", 1, 9, "auto_reply", 100, now),
        ], maxlen=200)

        mock_client = AsyncMock()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp = f.name
        orig = faq_module.FAQ_FILE
        faq_module.FAQ_FILE = tmp
        try:
            from unittest.mock import patch
            with patch("bot.faq.bot_stats", stats):
                result = await faq_module.generate_faq(mock_client)
            assert result == []  # no cache, no data
            mock_client.chat.completions.create.assert_not_called()
        finally:
            faq_module.FAQ_FILE = orig
            os.unlink(tmp)
