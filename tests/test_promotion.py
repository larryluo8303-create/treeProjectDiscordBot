"""Tests for the BigTreeSignal promotion modules.

Covers:
- promo_config: channel checks, CTA generation, frequency gating, embed builders
- scheduler: promo/lesson CRUD, JSON persistence, embed building
- testimonials: persistence, dedup, approved filtering
- listener: testimonial pattern matching
"""

import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import discord
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# promo_config tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsPromoChannel:
    @patch("bot.promo_config.PROMO_ENABLED", True)
    @patch("bot.promo_config.PROMO_CHANNEL_IDS", [111, 222, 333])
    def test_channel_in_list(self):
        from bot.promo_config import is_promo_channel
        assert is_promo_channel(222) is True

    @patch("bot.promo_config.PROMO_ENABLED", True)
    @patch("bot.promo_config.PROMO_CHANNEL_IDS", [111, 222, 333])
    def test_channel_not_in_list(self):
        from bot.promo_config import is_promo_channel
        assert is_promo_channel(999) is False

    @patch("bot.promo_config.PROMO_ENABLED", False)
    @patch("bot.promo_config.PROMO_CHANNEL_IDS", [111])
    def test_disabled_returns_false(self):
        from bot.promo_config import is_promo_channel
        assert is_promo_channel(111) is False

    @patch("bot.promo_config.PROMO_ENABLED", True)
    @patch("bot.promo_config.PROMO_CHANNEL_IDS", [])
    def test_empty_list_returns_false(self):
        from bot.promo_config import is_promo_channel
        assert is_promo_channel(111) is False


class TestShouldAppendCta:
    @patch("bot.promo_config.PROMO_ENABLED", True)
    @patch("bot.promo_config.CTA_FREQUENCY", 5)
    def test_counter_hits_frequency(self):
        from bot.promo_config import should_append_cta
        assert should_append_cta(5) is True
        assert should_append_cta(10) is True
        assert should_append_cta(0) is True  # 0 % 5 == 0

    @patch("bot.promo_config.PROMO_ENABLED", True)
    @patch("bot.promo_config.CTA_FREQUENCY", 5)
    def test_counter_misses_frequency(self):
        from bot.promo_config import should_append_cta
        assert should_append_cta(1) is False
        assert should_append_cta(3) is False
        assert should_append_cta(7) is False

    @patch("bot.promo_config.PROMO_ENABLED", True)
    @patch("bot.promo_config.CTA_FREQUENCY", 0)
    def test_zero_frequency_disables(self):
        from bot.promo_config import should_append_cta
        assert should_append_cta(0) is False
        assert should_append_cta(5) is False

    @patch("bot.promo_config.PROMO_ENABLED", True)
    @patch("bot.promo_config.CTA_FREQUENCY", -1)
    def test_negative_frequency_disables(self):
        from bot.promo_config import should_append_cta
        assert should_append_cta(0) is False

    @patch("bot.promo_config.PROMO_ENABLED", False)
    @patch("bot.promo_config.CTA_FREQUENCY", 5)
    def test_disabled_promo(self):
        from bot.promo_config import should_append_cta
        assert should_append_cta(5) is False


class TestGetAutoReplyCta:
    @patch("bot.promo_config.AUTO_REPLY_CTA_TEXT", "test CTA")
    @patch("bot.promo_config.SIGNAL_PRODUCT_URL", "https://example.com")
    def test_with_url(self):
        from bot.promo_config import get_auto_reply_cta
        cta = get_auto_reply_cta()
        assert "test CTA" in cta
        assert "https://example.com" in cta
        assert cta.startswith("\n\n")

    @patch("bot.promo_config.AUTO_REPLY_CTA_TEXT", "test CTA")
    @patch("bot.promo_config.SIGNAL_PRODUCT_URL", "")
    def test_without_url(self):
        from bot.promo_config import get_auto_reply_cta
        cta = get_auto_reply_cta()
        assert "test CTA" in cta
        assert "https://" not in cta


class TestGetSignalCtaEmbed:
    @patch("bot.promo_config.SIGNAL_PRODUCT_NAME", "TestSignal")
    @patch("bot.promo_config.SIGNAL_CTA_TEXT", "Try our signals")
    @patch("bot.promo_config.SIGNAL_PRODUCT_URL", "https://test.com")
    @patch("bot.promo_config.FREE_TRIAL_ENABLED", False)
    @patch("bot.promo_config.FREE_TRIAL_URL", "")
    def test_basic_embed(self):
        from bot.promo_config import get_signal_cta_embed
        embed = get_signal_cta_embed()
        assert isinstance(embed, discord.Embed)
        assert "TestSignal" in embed.title
        assert embed.description == "Try our signals"
        # Should have market coverage + link fields
        assert len(embed.fields) == 2

    @patch("bot.promo_config.SIGNAL_PRODUCT_NAME", "TestSignal")
    @patch("bot.promo_config.SIGNAL_CTA_TEXT", "Try signals")
    @patch("bot.promo_config.SIGNAL_PRODUCT_URL", "https://test.com")
    @patch("bot.promo_config.FREE_TRIAL_ENABLED", True)
    @patch("bot.promo_config.FREE_TRIAL_URL", "https://trial.com")
    def test_embed_with_trial(self):
        from bot.promo_config import get_signal_cta_embed
        embed = get_signal_cta_embed()
        # market + link + trial = 3 fields
        assert len(embed.fields) == 3
        trial_field = embed.fields[2]
        assert "trial.com" in trial_field.value


class TestGetSignalProductEmbed:
    @patch("bot.promo_config.SIGNAL_PRODUCT_NAME", "BigTree")
    @patch("bot.promo_config.SIGNAL_PRODUCT_URL", "https://bt.com")
    @patch("bot.promo_config.FREE_TRIAL_ENABLED", False)
    @patch("bot.promo_config.FREE_TRIAL_URL", "")
    def test_product_embed(self):
        from bot.promo_config import get_signal_product_embed
        embed = get_signal_product_embed()
        assert isinstance(embed, discord.Embed)
        assert "BigTree" in embed.title
        # market + push method + subscribe link = 3 fields
        assert len(embed.fields) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# scheduler CRUD tests (uses temp files to avoid polluting data/)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchedulerPromoCrud:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._promos_file = os.path.join(self._tmpdir, "promos.json")

    def teardown_method(self):
        for f in [self._promos_file, self._promos_file + ".tmp"]:
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(self._tmpdir)

    @patch("bot.scheduler.PROMOS_FILE")
    def test_add_and_list(self, mock_file):
        mock_file.__str__ = lambda _: self._promos_file
        # Patch at module level to use temp file
        import bot.scheduler as sched
        orig = sched.PROMOS_FILE
        sched.PROMOS_FILE = self._promos_file
        try:
            dt = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
            promo = sched.add_promo(
                title="Test Promo",
                description="50% off",
                scheduled_at=dt,
                channel_ids=[111, 222],
                created_by=999,
                url="https://example.com",
            )
            assert promo["title"] == "Test Promo"
            assert promo["id"].startswith("promo_")
            assert promo["last_posted"] is None
            assert promo["cancelled"] is False

            result = sched.list_promos()
            assert len(result) == 1
            assert result[0]["title"] == "Test Promo"
        finally:
            sched.PROMOS_FILE = orig

    @patch("bot.scheduler.PROMOS_FILE")
    def test_cancel(self, mock_file):
        import bot.scheduler as sched
        orig = sched.PROMOS_FILE
        sched.PROMOS_FILE = self._promos_file
        try:
            dt = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
            promo = sched.add_promo("Sale", "Big sale", dt, [111], 999)
            pid = promo["id"]

            assert sched.cancel_promo(pid) is True
            # Cancelled promo should not appear in list
            assert len(sched.list_promos()) == 0
            # Cancelling again returns False
            assert sched.cancel_promo(pid) is False
        finally:
            sched.PROMOS_FILE = orig

    @patch("bot.scheduler.PROMOS_FILE")
    def test_cancel_nonexistent(self, mock_file):
        import bot.scheduler as sched
        orig = sched.PROMOS_FILE
        sched.PROMOS_FILE = self._promos_file
        try:
            assert sched.cancel_promo("promo_doesnt_exist") is False
        finally:
            sched.PROMOS_FILE = orig

    @patch("bot.scheduler.PROMOS_FILE")
    def test_trial_signal_type(self, mock_file):
        import bot.scheduler as sched
        orig = sched.PROMOS_FILE
        sched.PROMOS_FILE = self._promos_file
        try:
            dt = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
            promo = sched.add_promo(
                "Trial", "Free signal", dt, [111], 999,
                promo_type="trial_signal",
            )
            assert promo["type"] == "trial_signal"
        finally:
            sched.PROMOS_FILE = orig


class TestSyncAutoPushChannels:
    def test_updates_stale_youtube_and_promo_channels(self, tmp_path):
        import bot.scheduler as sched

        lessons_file = tmp_path / "lessons.json"
        promos_file = tmp_path / "promos.json"
        lessons_file.write_text(json.dumps([
            {
                "id": "lesson_old",
                "source": "youtube_monitor",
                "cancelled": False,
                "channel_ids": [111],
            }
        ]), encoding="utf-8")
        promos_file.write_text(json.dumps([
            {
                "id": "promo_old",
                "source": "promo_monitor",
                "cancelled": False,
                "channel_ids": [111],
            }
        ]), encoding="utf-8")

        orig_l, orig_p = sched.LESSONS_FILE, sched.PROMOS_FILE
        sched.LESSONS_FILE = str(lessons_file)
        sched.PROMOS_FILE = str(promos_file)
        try:
            with patch("bot.config.YOUTUBE_LESSON_PUSH_CHANNELS", [111, 222]), \
                 patch("bot.config.PROMO_PUSH_CHANNELS", [111, 222]), \
                 patch("bot.config.PROMO_CHANNEL_IDS", [111]):
                sched.sync_auto_push_channels()
            lessons = json.loads(lessons_file.read_text(encoding="utf-8"))
            promos = json.loads(promos_file.read_text(encoding="utf-8"))
            assert lessons[0]["channel_ids"] == [111, 222]
            assert promos[0]["channel_ids"] == [111, 222]
        finally:
            sched.LESSONS_FILE = orig_l
            sched.PROMOS_FILE = orig_p


class TestSchedulerLessonCrud:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._lessons_file = os.path.join(self._tmpdir, "lessons.json")

    def teardown_method(self):
        for f in [self._lessons_file, self._lessons_file + ".tmp"]:
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(self._tmpdir)

    @patch("bot.scheduler.LESSONS_FILE")
    def test_add_and_list(self, mock_file):
        import bot.scheduler as sched
        orig = sched.LESSONS_FILE
        sched.LESSONS_FILE = self._lessons_file
        try:
            dt = datetime(2024, 2, 1, 9, 0, tzinfo=timezone.utc)
            lesson = sched.add_lesson(
                title="Lesson 1",
                content="Introduction to trading",
                scheduled_at=dt,
                channel_ids=[111],
                created_by=999,
                repeat="weekly",
            )
            assert lesson["id"].startswith("lesson_")
            assert lesson["repeat"] == "weekly"
            assert lesson["last_posted"] is None

            result = sched.list_lessons()
            assert len(result) == 1
        finally:
            sched.LESSONS_FILE = orig

    @patch("bot.scheduler.LESSONS_FILE")
    def test_cancel_lesson(self, mock_file):
        import bot.scheduler as sched
        orig = sched.LESSONS_FILE
        sched.LESSONS_FILE = self._lessons_file
        try:
            dt = datetime(2024, 2, 1, 9, 0, tzinfo=timezone.utc)
            lesson = sched.add_lesson("L1", "Content", dt, [111], 999)
            lid = lesson["id"]

            assert sched.cancel_lesson(lid) is True
            assert len(sched.list_lessons()) == 0
            assert sched.cancel_lesson(lid) is False
        finally:
            sched.LESSONS_FILE = orig

    @patch("bot.scheduler.LESSONS_FILE")
    def test_cancel_nonexistent_lesson(self, mock_file):
        import bot.scheduler as sched
        orig = sched.LESSONS_FILE
        sched.LESSONS_FILE = self._lessons_file
        try:
            assert sched.cancel_lesson("lesson_nope") is False
        finally:
            sched.LESSONS_FILE = orig


class TestSchedulerJsonPersistence:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._file = os.path.join(self._tmpdir, "test.json")

    def teardown_method(self):
        for f in [self._file, self._file + ".tmp"]:
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(self._tmpdir)

    def test_load_missing_file(self):
        from bot.scheduler import _load_json
        assert _load_json(self._file) == []

    def test_load_corrupt_file(self):
        from bot.scheduler import _load_json
        with open(self._file, "w") as f:
            f.write("{corrupt json!!!")
        assert _load_json(self._file) == []

    def test_save_and_load(self):
        from bot.scheduler import _load_json, _save_json
        data = [{"id": "test_1", "value": "hello"}]
        _save_json(self._file, data)
        loaded = _load_json(self._file)
        assert loaded == data

    def test_atomic_write_no_tmp_leftover(self):
        from bot.scheduler import _save_json
        _save_json(self._file, [{"x": 1}])
        assert os.path.exists(self._file)
        assert not os.path.exists(self._file + ".tmp")


class TestSchedulerBuildPromoEmbed:
    def test_promo_embed(self):
        from bot.scheduler import SchedulerCog
        promo = {
            "type": "promo",
            "title": "Big Sale",
            "description": "50% off everything",
            "url": "https://sale.com",
        }
        embed = SchedulerCog._build_promo_embed(promo)
        assert isinstance(embed, discord.Embed)
        assert "Big Sale" in embed.title
        assert embed.description == "50% off everything"
        assert any("sale.com" in f.value for f in embed.fields)

    def test_trial_signal_embed(self):
        from bot.scheduler import SchedulerCog
        promo = {
            "type": "trial_signal",
            "title": "Free Signal Review",
            "description": "AAPL signal hit +5%",
            "url": "",
        }
        embed = SchedulerCog._build_promo_embed(promo)
        assert "Free Signal Review" in embed.title
        # Trial signal uses green color
        assert embed.color == discord.Color.green()

    def test_promo_embed_gold_color(self):
        from bot.scheduler import SchedulerCog
        promo = {
            "type": "promo",
            "title": "Sale",
            "description": "Desc",
            "url": "",
        }
        embed = SchedulerCog._build_promo_embed(promo)
        assert embed.color == discord.Color.gold()


# ═══════════════════════════════════════════════════════════════════════════════
# testimonials persistence tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTestimonialsPersistence:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._file = os.path.join(self._tmpdir, "testimonials.json")

    def teardown_method(self):
        for f in [self._file, self._file + ".tmp"]:
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(self._tmpdir)

    def test_load_empty(self):
        import bot.testimonials as tmod
        orig = tmod.TESTIMONIALS_FILE
        tmod.TESTIMONIALS_FILE = self._file
        try:
            assert tmod._load_testimonials() == []
        finally:
            tmod.TESTIMONIALS_FILE = orig

    def test_save_and_load(self):
        import bot.testimonials as tmod
        orig = tmod.TESTIMONIALS_FILE
        tmod.TESTIMONIALS_FILE = self._file
        try:
            data = [{"id": "test_abc", "status": "pending", "content": "great!"}]
            tmod._save_testimonials(data)
            loaded = tmod._load_testimonials()
            assert len(loaded) == 1
            assert loaded[0]["id"] == "test_abc"
        finally:
            tmod.TESTIMONIALS_FILE = orig

    def test_get_approved_only(self):
        import bot.testimonials as tmod
        orig = tmod.TESTIMONIALS_FILE
        tmod.TESTIMONIALS_FILE = self._file
        try:
            data = [
                {"id": "t1", "status": "pending", "content": "a"},
                {"id": "t2", "status": "approved", "content": "b"},
                {"id": "t3", "status": "rejected", "content": "c"},
                {"id": "t4", "status": "approved", "content": "d"},
            ]
            tmod._save_testimonials(data)
            approved = tmod.get_approved_testimonials(limit=10)
            assert len(approved) == 2
            assert all(t["status"] == "approved" for t in approved)
        finally:
            tmod.TESTIMONIALS_FILE = orig

    def test_get_approved_respects_limit(self):
        import bot.testimonials as tmod
        orig = tmod.TESTIMONIALS_FILE
        tmod.TESTIMONIALS_FILE = self._file
        try:
            data = [
                {"id": f"t{i}", "status": "approved", "content": f"msg {i}"}
                for i in range(10)
            ]
            tmod._save_testimonials(data)
            approved = tmod.get_approved_testimonials(limit=3)
            assert len(approved) == 3
            # Should be the last 3
            assert approved[0]["id"] == "t7"
        finally:
            tmod.TESTIMONIALS_FILE = orig


# ═══════════════════════════════════════════════════════════════════════════════
# listener testimonial pattern tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTestimonialPatterns:
    """Test the _TESTIMONIAL_PATTERNS regex from MessageListener."""

    PATTERN = re.compile(
        r"(赚了|賺了|盈利|翻倍|大赚|大賺|跟单|跟單|跟信号|跟信號|信号准|信號準|"
        r"赚到|賺到|出金|回本|赚钱|賺錢|收益不错|收益不錯|"
        r"profit|gains|made money|signal works|great signal|good signal)",
        re.IGNORECASE,
    )

    # Positive matches
    def test_simplified_profit(self):
        assert self.PATTERN.search("跟信号赚了不少钱")

    def test_traditional_profit(self):
        assert self.PATTERN.search("跟信號賺了")

    def test_profit_gains(self):
        assert self.PATTERN.search("盈利了20%")

    def test_doubled(self):
        assert self.PATTERN.search("这波翻倍了！")

    def test_follow_signal(self):
        assert self.PATTERN.search("跟单大赚")

    def test_signal_accurate(self):
        assert self.PATTERN.search("信号准得很")

    def test_made_money(self):
        assert self.PATTERN.search("I made money following the signal")

    def test_english_profit(self):
        assert self.PATTERN.search("huge profit today")

    def test_gains(self):
        assert self.PATTERN.search("great gains this week")

    def test_signal_works(self):
        assert self.PATTERN.search("The signal works perfectly!")

    def test_great_signal(self):
        assert self.PATTERN.search("Great signal on AAPL")

    def test_good_signal(self):
        assert self.PATTERN.search("good signal!")

    def test_withdraw(self):
        assert self.PATTERN.search("成功出金了")

    def test_breakeven(self):
        assert self.PATTERN.search("终于回本了")

    def test_returns_good(self):
        assert self.PATTERN.search("收益不错")

    def test_traditional_returns(self):
        assert self.PATTERN.search("收益不錯啊")

    # Negative matches — normal messages should NOT match
    def test_normal_question(self):
        assert not self.PATTERN.search("AAPL怎么看？")

    def test_greeting(self):
        assert not self.PATTERN.search("大家好")

    def test_analysis(self):
        assert not self.PATTERN.search("大盘走势分析")

    def test_empty(self):
        assert not self.PATTERN.search("")


# ═══════════════════════════════════════════════════════════════════════════════
# scheduler multiple promos / edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchedulerEdgeCases:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._promos_file = os.path.join(self._tmpdir, "promos.json")
        self._lessons_file = os.path.join(self._tmpdir, "lessons.json")

    def teardown_method(self):
        for f in [self._promos_file, self._promos_file + ".tmp",
                  self._lessons_file, self._lessons_file + ".tmp"]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(self._tmpdir):
            os.rmdir(self._tmpdir)

    def test_multiple_promos_independent(self):
        import bot.scheduler as sched
        orig = sched.PROMOS_FILE
        sched.PROMOS_FILE = self._promos_file
        try:
            dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
            p1 = sched.add_promo("P1", "D1", dt, [1], 99)
            p2 = sched.add_promo("P2", "D2", dt, [2], 99)
            p3 = sched.add_promo("P3", "D3", dt, [3], 99)

            assert len(sched.list_promos()) == 3

            sched.cancel_promo(p2["id"])
            remaining = sched.list_promos()
            assert len(remaining) == 2
            assert all(p["id"] != p2["id"] for p in remaining)
        finally:
            sched.PROMOS_FILE = orig

    def test_cannot_cancel_posted_promo(self):
        import bot.scheduler as sched
        orig = sched.PROMOS_FILE
        sched.PROMOS_FILE = self._promos_file
        try:
            dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
            promo = sched.add_promo("P", "D", dt, [1], 99)
            # Simulate it being posted
            data = sched._load_json(self._promos_file)
            data[0]["posted"] = True
            sched._save_json(self._promos_file, data)

            assert sched.cancel_promo(promo["id"]) is False
        finally:
            sched.PROMOS_FILE = orig

    def test_lesson_repeat_modes_stored(self):
        import bot.scheduler as sched
        orig = sched.LESSONS_FILE
        sched.LESSONS_FILE = self._lessons_file
        try:
            dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
            l1 = sched.add_lesson("L1", "C1", dt, [1], 99, repeat="daily")
            l2 = sched.add_lesson("L2", "C2", dt, [1], 99, repeat="weekly")
            l3 = sched.add_lesson("L3", "C3", dt, [1], 99, repeat="none")

            lessons = sched.list_lessons()
            repeats = {ls["id"]: ls["repeat"] for ls in lessons}
            assert repeats[l1["id"]] == "daily"
            assert repeats[l2["id"]] == "weekly"
            assert repeats[l3["id"]] == "none"
        finally:
            sched.LESSONS_FILE = orig
