"""Tests for bot.daily_summary — GPT-powered daily owner message summary."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


# ── _seconds_until_next tests ─────────────────────────────────────────────


class TestSecondsUntilNext:
    """Test the scheduling logic for daily summary."""

    def _make_cog(self):
        from unittest.mock import MagicMock
        from bot.daily_summary import DailySummaryCog
        bot = MagicMock()
        openai_client = MagicMock()
        return DailySummaryCog(bot, openai_client)

    @patch("bot.daily_summary.DAILY_SUMMARY_DAYS", [0, 1, 2, 3, 4])
    @patch("bot.daily_summary.DAILY_SUMMARY_HOUR", 16)
    @patch("bot.daily_summary.DAILY_SUMMARY_MINUTE", 0)
    def test_same_day_before_target(self):
        """On a weekday before target time, should schedule for today."""
        cog = self._make_cog()
        ET = timezone(timedelta(hours=-4))
        # Wednesday 10:00 ET → target is today 16:00
        fake_now = datetime(2026, 8, 12, 10, 0, 0, tzinfo=ET)  # Wednesday
        with patch("bot.daily_summary.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            secs = cog._seconds_until_next()
        assert 21500 < secs < 21700  # ~6 hours

    @patch("bot.daily_summary.DAILY_SUMMARY_DAYS", [0, 1, 2, 3, 4])
    @patch("bot.daily_summary.DAILY_SUMMARY_HOUR", 16)
    @patch("bot.daily_summary.DAILY_SUMMARY_MINUTE", 0)
    def test_same_day_after_target(self):
        """On a weekday after target time, should schedule for next weekday."""
        cog = self._make_cog()
        ET = timezone(timedelta(hours=-4))
        # Wednesday 17:00 ET → next is Thursday 16:00
        fake_now = datetime(2026, 8, 12, 17, 0, 0, tzinfo=ET)  # Wednesday
        with patch("bot.daily_summary.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            secs = cog._seconds_until_next()
        assert 82000 < secs < 83000  # ~23 hours

    @patch("bot.daily_summary.DAILY_SUMMARY_DAYS", [0, 1, 2, 3, 4])
    @patch("bot.daily_summary.DAILY_SUMMARY_HOUR", 16)
    @patch("bot.daily_summary.DAILY_SUMMARY_MINUTE", 0)
    def test_friday_after_target_skips_weekend(self):
        """On Friday after target, should skip to Monday."""
        cog = self._make_cog()
        ET = timezone(timedelta(hours=-4))
        # Friday 17:00 ET → next is Monday 16:00 (3 days - 1 hour)
        fake_now = datetime(2026, 8, 14, 17, 0, 0, tzinfo=ET)  # Friday
        with patch("bot.daily_summary.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            secs = cog._seconds_until_next()
        # 3 days minus 1 hour = 259200 - 3600 = 255600
        assert 255000 < secs < 256000

    @patch("bot.daily_summary.DAILY_SUMMARY_DAYS", [0, 1, 2, 3, 4])
    @patch("bot.daily_summary.DAILY_SUMMARY_HOUR", 16)
    @patch("bot.daily_summary.DAILY_SUMMARY_MINUTE", 0)
    def test_after_early_run_skips_todays_slot(self):
        """If already posted today, next run must not be today's 16:00."""
        cog = self._make_cog()
        ET = timezone(timedelta(hours=-4))
        today = datetime(2026, 8, 28, 15, 59, 54, tzinfo=ET).date()

        def posted(date):
            return date == today

        fake_now = datetime(2026, 8, 28, 15, 59, 54, tzinfo=ET)
        with patch("bot.daily_summary.datetime") as mock_dt, \
             patch.object(cog, "_already_posted_on_date", side_effect=posted):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            secs = cog._seconds_until_next()
        # Aug 28 2026 is Friday; next weekday is Monday ≈ 72h
        assert 258000 < secs < 260000


class TestDuplicatePrevention:
    @pytest.mark.asyncio
    async def test_run_summary_skips_if_already_posted_today(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from bot.daily_summary import DailySummaryCog

        cog = DailySummaryCog(MagicMock(), AsyncMock())
        with patch.object(cog, "_already_posted_on_date", return_value=True), \
             patch("bot.daily_summary.collect_owner_messages", new=AsyncMock()) as mock_collect:
            await cog._run_summary()
            mock_collect.assert_not_called()


# ── generate_daily_summary tests ──────────────────────────────────────────


class TestGenerateDailySummary:
    @pytest.mark.asyncio
    async def test_returns_gpt_response(self):
        from unittest.mock import AsyncMock, MagicMock
        from bot.daily_summary import generate_daily_summary

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "今日总结内容"
        mock_client.chat.completions.create.return_value = mock_response

        result = await generate_daily_summary(mock_client, "test messages")
        assert result == "今日总结内容"

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        from unittest.mock import AsyncMock
        from bot.daily_summary import generate_daily_summary

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        result = await generate_daily_summary(mock_client, "test messages")
        assert result == ""
