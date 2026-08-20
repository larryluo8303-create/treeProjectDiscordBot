"""Tests for bot.ingestion_scheduler module — status reporting and cog init."""

from unittest.mock import MagicMock

from bot.ingestion_scheduler import IngestionSchedulerCog


class TestIngestionSchedulerCogInit:
    def test_init(self):
        bot = MagicMock()
        cog = IngestionSchedulerCog(bot)
        assert cog.bot is bot
        assert cog._ingest_task is None
        assert cog._style_task is None
        assert cog._last_ingest is None
        assert cog._last_style is None


class TestIngestionSchedulerStatus:
    def test_status_initial(self):
        bot = MagicMock()
        cog = IngestionSchedulerCog(bot)
        status = cog.status()
        assert "ingest_interval_hours" in status
        assert "style_interval_hours" in status
        assert status["last_ingest"] is None
        assert status["last_style"] is None

    def test_status_after_ingest(self):
        from datetime import datetime, timezone
        bot = MagicMock()
        cog = IngestionSchedulerCog(bot)
        cog._last_ingest = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        status = cog.status()
        assert status["last_ingest"] is not None
        assert "2024-01-15" in status["last_ingest"]

    def test_status_after_style(self):
        from datetime import datetime, timezone
        bot = MagicMock()
        cog = IngestionSchedulerCog(bot)
        cog._last_style = datetime(2024, 6, 1, 8, 30, tzinfo=timezone.utc)
        status = cog.status()
        assert status["last_style"] is not None
        assert "2024-06-01" in status["last_style"]
