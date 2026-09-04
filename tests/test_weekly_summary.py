"""Tests for bot.weekly_summary — GPT-powered weekly owner message summary."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── format_messages_for_gpt tests ────────────────────────────────────────────


class TestFormatMessagesForGpt:
    def test_empty_list(self):
        from bot.weekly_summary import format_messages_for_gpt
        assert format_messages_for_gpt([]) == ""

    def test_basic_format(self):
        from bot.weekly_summary import format_messages_for_gpt
        msgs = [
            {"channel": "general", "time": "08/10 14:00", "content": "Hello world", "is_reply": False},
            {"channel": "trading", "time": "08/10 15:00", "content": "[回复 User1: question]\nanswer", "is_reply": True},
        ]
        result = format_messages_for_gpt(msgs)
        assert "[08/10 14:00] #general [发帖] Hello world" in result
        assert "[08/10 15:00] #trading [回复]" in result
        assert "answer" in result

    def test_truncation(self):
        from bot.weekly_summary import format_messages_for_gpt, _MAX_CONTENT_CHARS
        # Create messages that exceed the char limit
        msgs = [
            {"channel": "ch", "time": "08/10 10:00", "content": "x" * 5000, "is_reply": False}
            for _ in range(20)
        ]
        result = format_messages_for_gpt(msgs)
        assert len(result) <= _MAX_CONTENT_CHARS + 200  # some overhead for truncation message
        assert "内容已截断" in result


# ── collect_owner_messages tests ─────────────────────────────────────────────


class TestCollectOwnerMessages:
    @pytest.mark.asyncio
    async def test_collects_owner_messages(self):
        from bot.weekly_summary import collect_owner_messages

        owner_id = 12345
        since = datetime(2026, 8, 1, tzinfo=timezone.utc)

        msg1 = MagicMock()
        msg1.author.id = owner_id
        msg1.content = "Market analysis for today"
        msg1.created_at = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        msg1.reference = None

        msg2 = MagicMock()
        msg2.author.id = 99999  # not owner
        msg2.content = "Random message"
        msg2.created_at = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)

        msg3 = MagicMock()
        msg3.author.id = owner_id
        msg3.content = ""  # empty content, should be skipped
        msg3.created_at = datetime(2026, 8, 10, 16, 0, tzinfo=timezone.utc)

        channel = AsyncMock()
        channel.name = "trading"

        async def mock_history(**kwargs):
            for m in [msg1, msg2, msg3]:
                yield m

        channel.history = mock_history

        bot = MagicMock()
        bot.get_channel.return_value = channel

        messages, errors = await collect_owner_messages(bot, [111], owner_id, since)
        assert errors == []
        assert len(messages) == 1
        assert messages[0]["content"] == "Market analysis for today"
        assert messages[0]["channel"] == "trading"
        assert messages[0]["is_reply"] is False

    @pytest.mark.asyncio
    async def test_collects_replies_with_context(self):
        from bot.weekly_summary import collect_owner_messages

        owner_id = 12345
        since = datetime(2026, 8, 1, tzinfo=timezone.utc)

        original_msg = MagicMock()
        original_msg.content = "What should I do about SPY?"
        original_msg.author.display_name = "TestUser"

        ref = MagicMock()
        ref.message_id = 777
        ref.resolved = original_msg

        msg1 = MagicMock()
        msg1.author.id = owner_id
        msg1.content = "Great question, the answer is..."
        msg1.created_at = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        msg1.reference = ref

        channel = AsyncMock()
        channel.name = "general"
        channel.fetch_message = AsyncMock(return_value=original_msg)

        async def mock_history(**kwargs):
            yield msg1

        channel.history = mock_history

        bot = MagicMock()
        bot.get_channel.return_value = channel

        messages, errors = await collect_owner_messages(bot, [111], owner_id, since)
        assert errors == []
        assert len(messages) == 1
        assert messages[0]["is_reply"] is True
        assert "TestUser" in messages[0]["content"]
        assert "SPY" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_skips_inaccessible_channels(self):
        from bot.weekly_summary import collect_owner_messages

        bot = MagicMock()
        bot.get_channel.return_value = None
        bot.fetch_channel = AsyncMock(side_effect=Exception("Not found"))

        messages, errors = await collect_owner_messages(bot, [999], 12345, datetime.now(timezone.utc))
        assert messages == []
        assert len(errors) == 1
        assert "999" in errors[0]

    @pytest.mark.asyncio
    async def test_history_network_error_is_reported(self):
        from bot.weekly_summary import collect_owner_messages

        channel = AsyncMock()
        channel.name = "trading"
        channel.history = MagicMock(side_effect=OSError("getaddrinfo failed"))

        bot = MagicMock()
        bot.get_channel.return_value = channel

        messages, errors = await collect_owner_messages(
            bot, [111], 12345, datetime.now(timezone.utc),
        )
        assert messages == []
        assert len(errors) == 1
        assert "getaddrinfo" in errors[0] or "111" in errors[0]

# ── _seconds_until_next tests ────────────────────────────────────────────────


class TestSecondsUntilNext:
    def test_future_this_week(self):
        """If target day is later this week, should be within 7 days."""
        from bot.weekly_summary import WeeklySummaryCog, _ET
        cog = WeeklySummaryCog.__new__(WeeklySummaryCog)

        # Mock: Wednesday 10AM ET, target Saturday 14:00 ET
        fake_now = datetime(2026, 8, 12, 10, 0, 0, tzinfo=_ET)  # Wednesday
        with patch("bot.weekly_summary.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch("bot.weekly_summary.WEEKLY_SUMMARY_DAY", 5), \
                 patch("bot.weekly_summary.WEEKLY_SUMMARY_HOUR", 14):
                secs = cog._seconds_until_next()
                # Wednesday to Saturday = 3 days + 4 hours = ~277200 seconds
                assert 0 < secs <= 7 * 24 * 3600

    def test_past_this_week_goes_next_week(self):
        """If target day already passed this week, should be next week."""
        from bot.weekly_summary import WeeklySummaryCog, _ET
        cog = WeeklySummaryCog.__new__(WeeklySummaryCog)

        # Mock: Sunday 10AM ET, target Saturday 14:00 ET (already passed)
        fake_now = datetime(2026, 8, 16, 10, 0, 0, tzinfo=_ET)  # Sunday
        with patch("bot.weekly_summary.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch("bot.weekly_summary.WEEKLY_SUMMARY_DAY", 5), \
                 patch("bot.weekly_summary.WEEKLY_SUMMARY_HOUR", 14):
                secs = cog._seconds_until_next()
                # Should be ~6 days
                assert 5 * 24 * 3600 < secs <= 7 * 24 * 3600


class TestIsDue:
    def test_due_within_grace_if_not_posted(self):
        from bot.weekly_summary import WeeklySummaryCog, _ET

        cog = WeeklySummaryCog.__new__(WeeklySummaryCog)
        # Sunday 02:00 ET, target was Saturday 20:05 → within 18h grace
        fake_now = datetime(2026, 8, 23, 2, 0, 0, tzinfo=_ET)
        with patch("bot.weekly_summary.datetime") as mock_dt, \
             patch("bot.weekly_summary.WEEKLY_SUMMARY_DAY", 5), \
             patch("bot.weekly_summary.WEEKLY_SUMMARY_HOUR", 20), \
             patch("bot.weekly_summary.WEEKLY_SUMMARY_MINUTE", 5), \
             patch.object(cog, "_already_posted_since", return_value=False):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert cog._is_due(grace_hours=18) is True

    def test_not_due_after_grace(self):
        from bot.weekly_summary import WeeklySummaryCog, _ET

        cog = WeeklySummaryCog.__new__(WeeklySummaryCog)
        # Monday 16:00 ET — more than 18h after Sat 20:05
        fake_now = datetime(2026, 8, 24, 16, 0, 0, tzinfo=_ET)
        with patch("bot.weekly_summary.datetime") as mock_dt, \
             patch("bot.weekly_summary.WEEKLY_SUMMARY_DAY", 5), \
             patch("bot.weekly_summary.WEEKLY_SUMMARY_HOUR", 20), \
             patch("bot.weekly_summary.WEEKLY_SUMMARY_MINUTE", 5), \
             patch.object(cog, "_already_posted_since", return_value=False):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert cog._is_due(grace_hours=18) is False


class TestRunSummaryStatus:
    @pytest.mark.asyncio
    async def test_channel_errors_return_failed_not_empty(self):
        from bot.weekly_summary import WeeklySummaryCog

        cog = WeeklySummaryCog(MagicMock(), AsyncMock())
        with patch(
            "bot.weekly_summary.collect_owner_messages",
            new=AsyncMock(return_value=([], ["error reading channel 1: dns"])),
        ), patch("bot.weekly_summary.WEEKLY_SUMMARY_CHANNELS", [1]):
            status = await cog._run_summary()
        assert status == "failed"

    @pytest.mark.asyncio
    async def test_no_messages_returns_empty(self):
        from bot.weekly_summary import WeeklySummaryCog

        cog = WeeklySummaryCog(MagicMock(), AsyncMock())
        with patch(
            "bot.weekly_summary.collect_owner_messages",
            new=AsyncMock(return_value=([], [])),
        ), patch("bot.weekly_summary.WEEKLY_SUMMARY_CHANNELS", [1]):
            status = await cog._run_summary()
        assert status == "empty"


# ── generate_summary tests ──────────────────────────────────────────────────


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_returns_summary(self):
        from bot.weekly_summary import generate_summary

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "## 本周重点\n- 看涨SPY"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await generate_summary(mock_client, "test messages")
        assert "本周重点" in result

    @pytest.mark.asyncio
    async def test_handles_error(self):
        from bot.weekly_summary import generate_summary

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        result = await generate_summary(mock_client, "test messages")
        assert result == ""


# ── Config tests ─────────────────────────────────────────────────────────────


class TestWeeklySummaryConfig:
    def test_defaults(self):
        from bot.config import (
            WEEKLY_SUMMARY_ENABLED,
            WEEKLY_SUMMARY_DAY,
            WEEKLY_SUMMARY_HOUR,
        )
        assert WEEKLY_SUMMARY_ENABLED is False
        assert WEEKLY_SUMMARY_DAY == 5  # Saturday
        assert WEEKLY_SUMMARY_HOUR == 14  # 2PM ET
