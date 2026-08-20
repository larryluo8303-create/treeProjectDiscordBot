"""Tests for bot.stats module."""

import json
import os
import tempfile

from bot.stats import BotStats, QueryRecord


class TestBotStatsRecording:
    def test_record_query_increments_counters(self):
        stats = BotStats.__new__(BotStats)
        stats.total_queries = 0
        stats.auto_replies = 0
        stats.forwards = 0
        stats.total_confidence = 0
        stats.total_latency_ms = 0
        stats.channel_counts = {}
        stats._dirty = False
        stats._save_task = None
        from collections import deque
        stats.recent = deque(maxlen=200)

        stats.record_query("test?", 123, 8, "auto_reply", 150)
        assert stats.total_queries == 1
        assert stats.auto_replies == 1
        assert stats.forwards == 0
        assert stats.total_confidence == 8
        assert stats.total_latency_ms == 150
        assert stats.channel_counts[123] == 1
        assert stats._dirty is True

    def test_record_forward(self):
        stats = BotStats.__new__(BotStats)
        stats.total_queries = 0
        stats.auto_replies = 0
        stats.forwards = 0
        stats.total_confidence = 0
        stats.total_latency_ms = 0
        stats.channel_counts = {}
        stats._dirty = False
        stats._save_task = None
        from collections import deque
        stats.recent = deque(maxlen=200)

        stats.record_query("q?", 456, 3, "forward", 200)
        assert stats.forwards == 1
        assert stats.auto_replies == 0

    def test_avg_confidence(self):
        stats = BotStats.__new__(BotStats)
        stats.total_queries = 4
        stats.total_confidence = 28
        stats.total_latency_ms = 0
        assert stats.avg_confidence == 7.0

    def test_avg_confidence_zero_queries(self):
        stats = BotStats.__new__(BotStats)
        stats.total_queries = 0
        stats.total_confidence = 0
        stats.total_latency_ms = 0
        assert stats.avg_confidence == 0.0

    def test_snapshot(self):
        stats = BotStats.__new__(BotStats)
        stats.total_queries = 10
        stats.auto_replies = 7
        stats.forwards = 3
        stats.total_confidence = 65
        stats.total_latency_ms = 1500
        stats.channel_counts = {1: 5, 2: 3, 3: 2}
        from collections import deque
        import time
        stats.recent = deque()
        now = time.time()
        for i in range(7):
            stats.recent.append(QueryRecord(
                question=f"q{i}", channel_id=(i % 3) + 1,
                confidence=6 + (i % 3), action="auto_reply",
                latency_ms=150, timestamp=now - i,
            ))
        for i in range(3):
            stats.recent.append(QueryRecord(
                question=f"fwd{i}", channel_id=(i % 3) + 1,
                confidence=7, action="forward",
                latency_ms=150, timestamp=now - 7 - i,
            ))

        snap = stats.snapshot()
        assert snap["total_queries"] == 10
        assert snap["auto_replies"] == 7
        assert snap["forwards"] == 3


class TestBotStatsPersistence:
    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            import bot.stats as stats_module
            original_file = stats_module.STATS_FILE
            stats_module.STATS_FILE = tmp_path

            stats = BotStats.__new__(BotStats)
            stats.total_queries = 5
            stats.auto_replies = 3
            stats.forwards = 2
            stats.total_confidence = 35
            stats.total_latency_ms = 800
            stats.channel_counts = {100: 3, 200: 2}
            stats._dirty = True
            stats._save_task = None
            from collections import deque
            stats.recent = deque(maxlen=200)

            stats._save()

            stats2 = BotStats.__new__(BotStats)
            stats2.total_queries = 0
            stats2.auto_replies = 0
            stats2.forwards = 0
            stats2.total_confidence = 0
            stats2.total_latency_ms = 0
            stats2.channel_counts = {}
            stats2.recent = deque(maxlen=200)
            stats2._dirty = False
            stats2._save_task = None
            stats2._load()

            assert stats2.total_queries == 5
            assert stats2.auto_replies == 3
            assert stats2.channel_counts[100] == 3
        finally:
            stats_module.STATS_FILE = original_file
            os.unlink(tmp_path)

    def test_load_missing_file(self):
        import bot.stats as stats_module
        original_file = stats_module.STATS_FILE
        stats_module.STATS_FILE = "/nonexistent/stats.json"
        try:
            stats = BotStats.__new__(BotStats)
            stats.total_queries = 0
            stats.auto_replies = 0
            stats.forwards = 0
            stats.total_confidence = 0
            stats.total_latency_ms = 0
            stats.channel_counts = {}
            from collections import deque
            stats.recent = deque(maxlen=200)
            stats._dirty = False
            stats._save_task = None
            stats._load()
            assert stats.total_queries == 0
        finally:
            stats_module.STATS_FILE = original_file


class TestTopQuestions:
    def test_returns_recent(self):
        stats = BotStats.__new__(BotStats)
        stats.total_queries = 0
        stats.auto_replies = 0
        stats.forwards = 0
        stats.total_confidence = 0
        stats.total_latency_ms = 0
        stats.channel_counts = {}
        stats._dirty = False
        stats._save_task = None
        from collections import deque
        stats.recent = deque(maxlen=200)

        stats.record_query("q1?", 1, 5, "auto_reply", 100)
        stats.record_query("q2?", 1, 7, "forward", 200)
        stats.record_query("q3?", 1, 9, "auto_reply", 50)

        top = stats.top_questions(2)
        assert len(top) == 2
        assert top[0]["question"] == "q3?"
        assert top[1]["question"] == "q2?"
