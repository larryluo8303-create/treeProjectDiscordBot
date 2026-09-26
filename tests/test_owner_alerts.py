"""Tests for bot.owner_alerts — owner-only anomaly DM alerts.

All DM sends are mocked; no real Discord traffic.
"""

import time
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import bot.owner_alerts as oa


@pytest.fixture(autouse=True)
def clean_state():
    oa.reset_alert_state()
    yield
    oa.reset_alert_state()


@pytest.fixture()
def owner_id(monkeypatch):
    monkeypatch.setattr(oa, "OWNER_USER_ID", 12345)
    return 12345


def _fake_bot():
    owner = AsyncMock()
    bot = MagicMock()
    bot.fetch_user = AsyncMock(return_value=owner)
    return bot, owner


# ── 429 alerts ─────────────────────────────────────────────────────────────

async def test_429_threshold_triggers_dm(owner_id):
    bot, owner = _fake_bot()
    for _ in range(3):
        oa.record_openai_429()
    await oa.evaluate_and_alert(bot)
    owner.send.assert_called_once()
    embed = owner.send.call_args.kwargs["embed"]
    assert "429" in embed.title


async def test_429_below_threshold_stays_silent(owner_id):
    bot, owner = _fake_bot()
    for _ in range(2):
        oa.record_openai_429()
    await oa.evaluate_and_alert(bot)
    owner.send.assert_not_called()


async def test_429_cooldown_bounds_repeat_dms(owner_id):
    bot, owner = _fake_bot()
    for _ in range(3):
        oa.record_openai_429()
    await oa.evaluate_and_alert(bot)
    await oa.evaluate_and_alert(bot)
    owner.send.assert_called_once()


async def test_429_outside_window_ignored(owner_id, monkeypatch):
    bot, owner = _fake_bot()
    old = time.time() - 3600
    oa._openai_429_events.extend([old, old, old])
    await oa.evaluate_and_alert(bot)
    owner.send.assert_not_called()


# ── quota alerts ───────────────────────────────────────────────────────────

async def test_quota_error_alerts_immediately(owner_id):
    bot, owner = _fake_bot()
    oa.record_openai_quota_error()
    await oa.evaluate_and_alert(bot)
    owner.send.assert_called_once()
    embed = owner.send.call_args.kwargs["embed"]
    assert "额度" in embed.title or "鉴权" in embed.title


# ── gateway reconnect storm ────────────────────────────────────────────────

async def test_reconnect_storm_triggers_dm(owner_id):
    bot, owner = _fake_bot()
    for _ in range(5):
        oa.record_gateway_reconnect()
    await oa.evaluate_and_alert(bot)
    owner.send.assert_called_once()
    embed = owner.send.call_args.kwargs["embed"]
    assert "重连" in embed.title


async def test_reconnect_below_threshold_silent(owner_id):
    bot, owner = _fake_bot()
    for _ in range(4):
        oa.record_gateway_reconnect()
    await oa.evaluate_and_alert(bot)
    owner.send.assert_not_called()


async def test_on_disconnect_records_event():
    cog = oa.OwnerAlertCog(MagicMock())
    assert len(oa._gateway_reconnects) == 0
    await cog.on_disconnect()
    assert len(oa._gateway_reconnects) == 1


# ── 403 spike ──────────────────────────────────────────────────────────────

async def test_403_spike_triggers_dm(owner_id):
    bot, owner = _fake_bot()
    for _ in range(5):
        oa.record_discord_403()
    await oa.evaluate_and_alert(bot)
    owner.send.assert_called_once()
    embed = owner.send.call_args.kwargs["embed"]
    assert "403" in embed.title


def test_note_discord_error_only_records_forbidden():
    err = discord.Forbidden(MagicMock(), "forbidden")
    oa.note_discord_error(err)
    assert len(oa._discord_403s) == 1
    oa.note_discord_error(ValueError("nope"))
    oa.note_discord_error(None)
    assert len(oa._discord_403s) == 1


# ── scheduler subtask failures ─────────────────────────────────────────────

async def test_scheduler_subtask_failure_alerts(owner_id):
    bot, owner = _fake_bot()
    oa.record_scheduler_subtask_failure("promos", RuntimeError("boom"))
    await oa.evaluate_and_alert(bot)
    owner.send.assert_called_once()
    embed = owner.send.call_args.kwargs["embed"]
    assert "promos" in embed.description


async def test_scheduler_failure_cooldown_per_name(owner_id):
    bot, owner = _fake_bot()
    oa.record_scheduler_subtask_failure("promos", RuntimeError("boom"))
    await oa.evaluate_and_alert(bot)
    # Same subtask failing again inside cooldown -> no second DM
    oa.record_scheduler_subtask_failure("promos", RuntimeError("boom again"))
    await oa.evaluate_and_alert(bot)
    assert owner.send.call_count == 1


# ── guards ─────────────────────────────────────────────────────────────────

async def test_no_owner_id_skips_silently(monkeypatch):
    monkeypatch.setattr(oa, "OWNER_USER_ID", 0)
    bot, owner = _fake_bot()
    for _ in range(5):
        oa.record_openai_429()
    await oa.evaluate_and_alert(bot)  # must not raise
    bot.fetch_user.assert_not_called()
    owner.send.assert_not_called()


async def test_dm_owner_fetch_failure_returns_false(owner_id):
    bot = MagicMock()
    bot.fetch_user = AsyncMock(side_effect=RuntimeError("network down"))
    assert await oa._dm_owner(bot, "t", "b") is False


async def test_dm_owner_send_failure_returns_false(owner_id):
    bot, owner = _fake_bot()
    owner.send = AsyncMock(side_effect=RuntimeError("cannot dm"))
    assert await oa._dm_owner(bot, "t", "b") is False


async def test_evaluate_never_raises_with_broken_bot(owner_id):
    broken = MagicMock()
    broken.fetch_user = AsyncMock(side_effect=Exception("boom"))
    for _ in range(5):
        oa.record_discord_403()
    await oa.evaluate_and_alert(broken)  # must not raise
