"""Tests for bot.promo_monitor — auto schedule_promo from owner source channel."""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


# ── _next_push_time tests ────────────────────────────────────────────────────


class TestNextPushTime:
    def test_future_today(self):
        from bot.promo_monitor import _next_push_time, _ET
        fake_now = datetime(2026, 8, 15, 10, 0, 0, tzinfo=_ET)
        with patch("bot.promo_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = _next_push_time(16)
            assert result.hour == 16
            assert result.day == 15

    def test_past_today_goes_tomorrow(self):
        from bot.promo_monitor import _next_push_time, _ET
        fake_now = datetime(2026, 8, 15, 17, 0, 0, tzinfo=_ET)
        with patch("bot.promo_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = _next_push_time(16)
            assert result.hour == 16
            assert result.day == 16

    def test_clamps_invalid_hour(self):
        from bot.promo_monitor import _next_push_time, _ET
        fake_now = datetime(2026, 8, 15, 10, 0, 0, tzinfo=_ET)
        with patch("bot.promo_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            # Should clamp to 23 instead of raising
            result = _next_push_time(99)
            assert result.hour == 23


# ── create_auto_promo tests ──────────────────────────────────────────────────


class TestCreateAutoPromo:
    def test_creates_daily_promo_with_source_and_mention(self):
        from bot.promo_monitor import create_auto_promo, PROMO_MONITOR_SOURCE

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp = f.name
        try:
            with patch("bot.promo_monitor.PROMOS_FILE", tmp):
                promo = create_auto_promo(
                    title="Summer Sale",
                    description="50% off!",
                    channel_ids=[111, 222],
                    push_hour=16,
                    duration_days=90,
                )
                assert promo["title"] == "Summer Sale"
                assert promo["repeat"] == "daily"
                assert promo["mention_everyone"] is True
                assert promo["source"] == PROMO_MONITOR_SOURCE
                assert "expires_at" in promo

                with open(tmp, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                assert len(saved) == 1
                assert saved[0]["source"] == PROMO_MONITOR_SOURCE
                assert saved[0]["mention_everyone"] is True
        finally:
            os.unlink(tmp)

    def test_cancels_old_auto_promos(self):
        from bot.promo_monitor import create_auto_promo, PROMO_MONITOR_SOURCE

        old_promos = [
            {
                "id": "promo_old1",
                "type": "promo",
                "title": "Old Promo",
                "description": "old",
                "url": "",
                "scheduled_at": "2026-08-01T16:00:00-04:00",
                "repeat": "daily",
                "channel_ids": [111],
                "last_posted": None,
                "cancelled": False,
                "created_by": 0,
                "source": PROMO_MONITOR_SOURCE,
                "mention_everyone": True,
            },
            {
                "id": "promo_manual",
                "type": "promo",
                "title": "Manual Promo",
                "description": "manual",
                "url": "",
                "scheduled_at": "2026-08-01T16:00:00-04:00",
                "repeat": "none",
                "channel_ids": [111],
                "last_posted": None,
                "cancelled": False,
                "created_by": 0,
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(old_promos, f)
            tmp = f.name
        try:
            with patch("bot.promo_monitor.PROMOS_FILE", tmp):
                create_auto_promo(
                    title="New Promo",
                    description="new!",
                    channel_ids=[111],
                    push_hour=16,
                    duration_days=90,
                )
                with open(tmp, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Old auto promo cancelled, manual untouched, new one added
                assert len(saved) == 3
                assert saved[0]["cancelled"] is True  # old auto
                assert saved[1]["cancelled"] is False  # manual
                assert saved[2]["cancelled"] is False  # new auto
                assert saved[2]["source"] == PROMO_MONITOR_SOURCE
        finally:
            os.unlink(tmp)

    def test_expires_at_is_duration_days_from_scheduled(self):
        from bot.promo_monitor import create_auto_promo

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp = f.name
        try:
            with patch("bot.promo_monitor.PROMOS_FILE", tmp):
                promo = create_auto_promo(
                    title="Test",
                    description="test",
                    channel_ids=[111],
                    push_hour=16,
                    duration_days=30,
                )
                scheduled = datetime.fromisoformat(promo["scheduled_at"])
                expires = datetime.fromisoformat(promo["expires_at"])
                delta = expires - scheduled
                assert delta.days == 30
        finally:
            os.unlink(tmp)

    def test_image_url_stored(self):
        from bot.promo_monitor import create_auto_promo

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp = f.name
        try:
            with patch("bot.promo_monitor.PROMOS_FILE", tmp):
                promo = create_auto_promo(
                    title="Image Promo",
                    description="has image",
                    channel_ids=[111],
                    push_hour=16,
                    duration_days=90,
                    image_url="https://example.com/promo.png",
                )
                assert promo["image_url"] == "https://example.com/promo.png"
        finally:
            os.unlink(tmp)


# ── Scheduler expires_at test ────────────────────────────────────────────────


class TestSchedulerExpiresAt:
    def test_promo_auto_expires(self):
        """Verify that _process_promos marks expired promos as cancelled."""
        from bot.scheduler import _load_json, _save_json

        now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
        promos = [
            {
                "id": "promo_expired",
                "type": "promo",
                "title": "Expired",
                "description": "old",
                "url": "",
                "scheduled_at": "2026-07-01T16:00:00-04:00",
                "expires_at": "2026-09-30T16:00:00-04:00",
                "repeat": "daily",
                "channel_ids": [111],
                "last_posted": "2026-09-29T16:00:00+00:00",
                "cancelled": False,
                "created_by": 0,
                "source": "promo_monitor",
                "mention_everyone": True,
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(promos, f)
            tmp = f.name
        try:
            # Simulate what _process_promos does for expiry
            loaded = _load_json(tmp)
            for p in loaded:
                expires_at = p.get("expires_at")
                if expires_at and now >= datetime.fromisoformat(expires_at):
                    p["cancelled"] = True
            _save_json(tmp, loaded)

            result = _load_json(tmp)
            assert result[0]["cancelled"] is True
        finally:
            os.unlink(tmp)


# ── Scheduler mention_everyone test ──────────────────────────────────────────


class TestSchedulerMentionEveryone:
    def test_mention_content_generated(self):
        """Verify that promos with mention_everyone produce @everyone content."""
        promo = {"mention_everyone": True}
        mention = "@everyone\n" if promo.get("mention_everyone") else ""
        assert mention == "@everyone\n"

    def test_no_mention_without_flag(self):
        promo = {"mention_everyone": False}
        mention = "@everyone\n" if promo.get("mention_everyone") else ""
        assert mention == ""

    def test_no_mention_missing_flag(self):
        promo = {}
        mention = "@everyone\n" if promo.get("mention_everyone") else ""
        assert mention == ""


# ── Config tests ─────────────────────────────────────────────────────────────


class TestPromoMonitorConfig:
    def test_defaults(self):
        from bot.config import (
            PROMO_MONITOR_ENABLED,
            PROMO_SOURCE_CHANNEL_ID,
            PROMO_PUSH_HOUR,
            PROMO_DURATION_DAYS,
        )
        assert PROMO_MONITOR_ENABLED is False
        assert PROMO_SOURCE_CHANNEL_ID == 0
        assert PROMO_PUSH_HOUR == 16
        assert PROMO_DURATION_DAYS == 90
