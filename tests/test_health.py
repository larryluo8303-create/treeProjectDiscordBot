"""Tests for bot.health module — uptime calculation and HealthCog."""

import time

from bot.health import uptime_seconds


class TestUptime:
    def test_uptime_positive(self):
        result = uptime_seconds()
        assert result >= 0.0

    def test_uptime_increases(self):
        t1 = uptime_seconds()
        time.sleep(0.02)
        t2 = uptime_seconds()
        assert t2 > t1

    def test_uptime_is_float(self):
        assert isinstance(uptime_seconds(), float)


class TestHealthCogInit:
    def test_cog_instantiation(self):
        from unittest.mock import MagicMock
        from bot.health import HealthCog

        bot = MagicMock()
        cog = HealthCog(bot)
        assert cog._heartbeat_task is None
        assert cog._http_runner is None
