"""Tests for bot.health_digest — owner daily health digest (DM-only)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import bot.health_digest as hd


def _summary(**over):
    base = {
        "date_str": "2026-09-26",
        "total_queries": 128,
        "auto_replies": 120,
        "forwards": 8,
        "avg_latency_ms": 3200.0,
        "p95_latency_ms": 9100,
        "errors_24h": 2,
        "rate_limited_24h": 5,
        "verdict": "✅ 运行正常",
    }
    base.update(over)
    return base


# ── formatting ─────────────────────────────────────────────────────────────

def test_build_digest_text_healthy():
    text = hd.build_digest_text(_summary())
    assert "📊 Bot 每日健康简报" in text
    assert "128" in text
    assert "120" in text and "8" in text
    assert "3.2s" in text            # avg latency formatted
    assert "9.1s" in text            # p95 formatted
    assert "错误数：2" in text
    assert "限流触发：5" in text
    assert "✅ 运行正常" in text


def test_build_digest_text_idle():
    text = hd.build_digest_text(_summary(total_queries=0, auto_replies=0,
                                        forwards=0, verdict="💤 过去 24 小时无查询"))
    assert "💤" in text


def test_fmt_latency_units():
    assert hd._fmt_latency(500) == "500ms"
    assert hd._fmt_latency(3200) == "3.2s"
    assert hd._fmt_latency(28751) == "28.8s"


# ── summary / verdict logic ────────────────────────────────────────────────

def _stub_stats(records, errors=0, limited=0):
    return SimpleNamespace(
        _filter_by_range=lambda key: records,
        error_count_24h=lambda: errors,
        rate_limited_count_24h=lambda: limited,
    )


def _rec(latency_ms, action="auto_reply"):
    return SimpleNamespace(action=action, latency_ms=latency_ms)


def test_compute_summary_healthy(monkeypatch):
    records = [_rec(3000) for _ in range(10)] + [_rec(2000, "forward")]
    monkeypatch.setattr(hd, "bot_stats", _stub_stats(records))
    s = hd.compute_summary()
    assert s["total_queries"] == 11
    assert s["auto_replies"] == 10
    assert s["forwards"] == 1
    assert s["verdict"].startswith("✅")


def test_compute_summary_idle(monkeypatch):
    monkeypatch.setattr(hd, "bot_stats", _stub_stats([]))
    s = hd.compute_summary()
    assert s["total_queries"] == 0
    assert "💤" in s["verdict"]


def test_compute_summary_high_errors_warns(monkeypatch):
    records = [_rec(1000) for _ in range(5)]
    monkeypatch.setattr(hd, "bot_stats", _stub_stats(records, errors=12))
    s = hd.compute_summary()
    assert s["verdict"].startswith("⚠️")
    assert "错误数" in s["verdict"]


def test_compute_summary_slow_p95_warns(monkeypatch):
    records = [_rec(30000) for _ in range(20)]
    monkeypatch.setattr(hd, "bot_stats", _stub_stats(records))
    s = hd.compute_summary()
    assert s["verdict"].startswith("⚠️")
    assert "p95" in s["verdict"]


# ── daily send gating ──────────────────────────────────────────────────────

def _after_hour():
    # 09:30 ET — after the default 08:00 digest hour
    from zoneinfo import ZoneInfo
    return datetime(2026, 9, 26, 9, 30, tzinfo=ZoneInfo("America/New_York"))


@pytest.fixture()
def iso_env(monkeypatch, tmp_path):
    monkeypatch.setattr(hd, "STATE_FILE", str(tmp_path / "digest_state.json"))
    monkeypatch.setattr(hd, "HEALTH_DIGEST_ENABLED", True)
    fake_stats = _stub_stats([_rec(1000)])
    monkeypatch.setattr(hd, "bot_stats", fake_stats)
    dm = AsyncMock(return_value=True)
    monkeypatch.setattr(hd, "_dm_owner", dm)
    return dm


async def test_maybe_send_due_sends_and_records(iso_env, tmp_path):
    bot = MagicMock()
    assert await hd.maybe_send_daily_digest(bot, _after_hour()) is True
    iso_env.assert_called_once()
    # state recorded — second call same day is a no-op
    iso_env.reset_mock()
    assert await hd.maybe_send_daily_digest(bot, _after_hour()) is False
    iso_env.assert_not_called()


async def test_maybe_send_before_hour_silent(iso_env):
    from zoneinfo import ZoneInfo
    early = datetime(2026, 9, 26, 7, 0, tzinfo=ZoneInfo("America/New_York"))
    assert await hd.maybe_send_daily_digest(MagicMock(), early) is False
    iso_env.assert_not_called()


async def test_maybe_send_disabled_silent(iso_env, monkeypatch):
    monkeypatch.setattr(hd, "HEALTH_DIGEST_ENABLED", False)
    assert await hd.maybe_send_daily_digest(MagicMock(), _after_hour()) is False
    iso_env.assert_not_called()


async def test_maybe_send_dm_failure_does_not_mark_sent(iso_env):
    iso_env.return_value = False
    assert await hd.maybe_send_daily_digest(MagicMock(), _after_hour()) is False
    # next call retries (state was not recorded)
    iso_env.return_value = True
    assert await hd.maybe_send_daily_digest(MagicMock(), _after_hour()) is True


async def test_maybe_send_never_touches_channels(iso_env):
    """The digest path must only use the owner DM helper, never channel.send."""
    bot = MagicMock()
    await hd.maybe_send_daily_digest(bot, _after_hour())
    bot.get_channel.assert_not_called()
    bot.fetch_channel.assert_not_called()
