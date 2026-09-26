"""Scheduler subtask isolation: mark_scheduler_tick and sync_auto_push_channels
must not be able to kill the 60s loop (regression test)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.scheduler import SchedulerCog


def _make_cog():
    cog = SchedulerCog(MagicMock())
    for name in (
        "_process_promos",
        "_process_lessons",
        "_process_reminders",
        "_process_faq_push",
        "_process_learning_gap_report",
    ):
        setattr(cog, name, AsyncMock())
    return cog


@pytest.mark.asyncio
async def test_tick_and_channel_sync_failures_do_not_kill_loop():
    """If mark_scheduler_tick or sync_auto_push_channels raises, the loop must
    continue with the remaining subtasks instead of dying."""
    cog = _make_cog()
    with patch("bot.scheduler.PROMO_ENABLED", True), \
         patch("bot.scheduler.FEATURE_SLA_MONITORING", False), \
         patch("bot.scheduler.mark_scheduler_tick", side_effect=RuntimeError("tick boom")), \
         patch("bot.scheduler.sync_auto_push_channels", side_effect=RuntimeError("sync boom")):
        # Must not raise — isolation catches both failures.
        await cog._check_scheduled.coro(cog)

    # Other subtasks still ran despite the two failures.
    cog._process_promos.assert_awaited_once()
    cog._process_lessons.assert_awaited_once()
    cog._process_reminders.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_still_recorded_on_success():
    cog = _make_cog()
    with patch("bot.scheduler.PROMO_ENABLED", False), \
         patch("bot.scheduler.FEATURE_SLA_MONITORING", False), \
         patch("bot.scheduler.mark_scheduler_tick") as tick:
        await cog._check_scheduled.coro(cog)
    tick.assert_called_once()
    cog._process_reminders.assert_awaited_once()
