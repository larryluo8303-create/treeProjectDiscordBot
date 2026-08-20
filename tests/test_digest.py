"""Tests for bot.digest module — DigestCog embed builder and scheduling logic."""

import asyncio
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.stats import BotStats, QueryRecord


def _make_stats(records: list[QueryRecord]) -> BotStats:
    """Create a BotStats instance pre-loaded with records (bypasses __init__)."""
    stats = BotStats.__new__(BotStats)
    stats.total_queries = len(records)
    stats.auto_replies = sum(1 for r in records if r.action == "auto_reply")
    stats.forwards = stats.total_queries - stats.auto_replies
    stats.total_confidence = sum(r.confidence for r in records)
    stats.total_latency_ms = sum(r.latency_ms for r in records)
    stats.channel_counts = {}
    stats._dirty = False
    stats._save_task = None
    stats.recent = deque(records, maxlen=200)
    return stats


class TestDigestStartedGuard:
    """Test that the _started flag prevents duplicate task creation."""

    @pytest.mark.asyncio
    async def test_on_ready_sets_started_flag(self):
        from bot.digest import DigestCog

        bot = MagicMock(spec=discord.Client)
        cog = DigestCog(bot)
        assert cog._started is False

        with patch("bot.digest.DIGEST_ENABLED", True):
            await cog.on_ready()
            assert cog._started is True
            first_task = cog._digest_task

            # Second on_ready should NOT create a new task
            await cog.on_ready()
            assert cog._digest_task is first_task

        # Clean up
        if cog._digest_task:
            cog._digest_task.cancel()
            try:
                await cog._digest_task
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_on_ready_skipped_when_disabled(self):
        from bot.digest import DigestCog

        bot = MagicMock(spec=discord.Client)
        cog = DigestCog(bot)

        with patch("bot.digest.DIGEST_ENABLED", False):
            await cog.on_ready()
            assert cog._started is False
            assert cog._digest_task is None


class TestBuildDigestEmbed:
    """Test _build_digest_embed via the DigestCog."""

    @pytest.mark.asyncio
    async def test_empty_digest(self):
        from bot.digest import DigestCog

        bot = MagicMock(spec=discord.Client)
        bot.get_channel = MagicMock(return_value=None)
        cog = DigestCog(bot)

        empty_stats = _make_stats([])
        with patch("bot.digest.bot_stats", empty_stats):
            embed = await cog._build_digest_embed()

        assert isinstance(embed, discord.Embed)
        assert "Daily Digest" in embed.title
        # Should contain the "Quiet Day" field
        field_names = [f.name for f in embed.fields]
        assert "💤 Quiet Day" in field_names

    @pytest.mark.asyncio
    async def test_digest_with_queries(self):
        from bot.digest import DigestCog

        bot = MagicMock(spec=discord.Client)
        ch_mock = MagicMock()
        ch_mock.name = "test-channel"
        bot.get_channel = MagicMock(return_value=ch_mock)

        now = time.time()
        records = [
            QueryRecord("AAPL怎么看？", 111, 8, "auto_reply", 120, now - 100),
            QueryRecord("BTC能买吗？", 111, 4, "forward", 300, now - 50),
            QueryRecord("大盘分析", 222, 9, "auto_reply", 80, now - 10),
        ]
        stats = _make_stats(records)
        cog = DigestCog(bot)

        with patch("bot.digest.bot_stats", stats):
            embed = await cog._build_digest_embed()

        assert isinstance(embed, discord.Embed)
        field_names = [f.name for f in embed.fields]
        assert "📈 Overview" in field_names
        # Should NOT have quiet day
        assert "💤 Quiet Day" not in field_names

        overview_field = next(f for f in embed.fields if f.name == "📈 Overview")
        assert "3" in overview_field.value  # total
        assert "2" in overview_field.value  # auto-replied

    @pytest.mark.asyncio
    async def test_digest_filters_by_24h(self):
        from bot.digest import DigestCog

        bot = MagicMock(spec=discord.Client)
        bot.get_channel = MagicMock(return_value=None)

        now = time.time()
        old_ts = now - 90000  # >24h ago
        records = [
            QueryRecord("old question", 111, 5, "auto_reply", 100, old_ts),
            QueryRecord("new question", 111, 8, "auto_reply", 100, now - 100),
        ]
        stats = _make_stats(records)
        cog = DigestCog(bot)

        with patch("bot.digest.bot_stats", stats):
            embed = await cog._build_digest_embed()

        overview = next(f for f in embed.fields if f.name == "📈 Overview")
        # Only the new question should be counted
        assert "Total questions:** 1" in overview.value

    @pytest.mark.asyncio
    async def test_digest_shows_forwarded_questions(self):
        from bot.digest import DigestCog

        bot = MagicMock(spec=discord.Client)
        bot.get_channel = MagicMock(return_value=None)

        now = time.time()
        records = [
            QueryRecord("forwarded q", 111, 3, "forward", 200, now - 10),
        ]
        stats = _make_stats(records)
        cog = DigestCog(bot)

        with patch("bot.digest.bot_stats", stats):
            embed = await cog._build_digest_embed()

        field_names = [f.name for f in embed.fields]
        assert "🔴 Forwarded / Unanswered" in field_names
