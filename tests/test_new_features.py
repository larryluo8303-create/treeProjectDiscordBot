"""Tests for all 12 new features."""

import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Feature 1: Language detection
# ---------------------------------------------------------------------------

class TestLangDetect:
    def test_detect_chinese(self):
        from bot.lang_detect import detect_language
        assert detect_language("你好，请问这个怎么用？") == "zh"

    def test_detect_english(self):
        from bot.lang_detect import detect_language
        assert detect_language("How does this work?") == "en"

    def test_detect_japanese(self):
        from bot.lang_detect import detect_language
        assert detect_language("これはどうやって使いますか？") == "ja"

    def test_detect_korean(self):
        from bot.lang_detect import detect_language
        assert detect_language("이것은 어떻게 사용합니까?") == "ko"

    def test_detect_empty(self):
        from bot.lang_detect import detect_language
        result = detect_language("")
        assert isinstance(result, str)

    def test_detect_mixed(self):
        from bot.lang_detect import detect_language
        # Mixed Chinese + English, Chinese chars dominate
        assert detect_language("这是一个test") == "zh"

    def test_get_reply_instruction_en(self):
        from bot.lang_detect import get_reply_lang_instruction
        instr = get_reply_lang_instruction("en")
        assert "English" in instr

    def test_get_reply_instruction_zh(self):
        from bot.lang_detect import get_reply_lang_instruction
        instr = get_reply_lang_instruction("zh")
        assert instr == ""  # default, no extra instruction

    def test_get_reply_instruction_ja(self):
        from bot.lang_detect import get_reply_lang_instruction
        instr = get_reply_lang_instruction("ja")
        assert "Japanese" in instr

    def test_get_reply_instruction_ko(self):
        from bot.lang_detect import get_reply_lang_instruction
        instr = get_reply_lang_instruction("ko")
        assert "Korean" in instr

    def test_get_reply_instruction_unknown(self):
        from bot.lang_detect import get_reply_lang_instruction
        instr = get_reply_lang_instruction("xx")
        assert instr == ""


# ---------------------------------------------------------------------------
# Feature 2: KB Report (tested via commands — module-level satisfaction_stats)
# ---------------------------------------------------------------------------

class TestFeedback:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.feedback_file = os.path.join(self.tmpdir, "feedback.json")

    def teardown_method(self):
        if os.path.exists(self.feedback_file):
            os.unlink(self.feedback_file)
        os.rmdir(self.tmpdir)

    def test_record_and_stats(self):
        with patch("bot.feedback.FEEDBACK_FILE", self.feedback_file):
            from bot.feedback import record_feedback, satisfaction_stats
            record_feedback(1, 100, 200, "test q", "test a", True)
            record_feedback(2, 100, 201, "test q2", "test a2", False)
            stats = satisfaction_stats(30)
            assert stats["total"] == 2
            assert stats["positive"] == 1
            assert stats["negative"] == 1
            assert stats["satisfaction_rate"] == 50.0

    def test_duplicate_feedback_updates(self):
        with patch("bot.feedback.FEEDBACK_FILE", self.feedback_file):
            from bot.feedback import record_feedback, _load
            record_feedback(1, 100, 200, "q", "a", True)
            record_feedback(1, 100, 200, "q", "a", False)
            records = _load()
            # Should be 1 record (updated, not duplicated)
            user_records = [r for r in records if r["message_id"] == 1 and r["user_id"] == 200]
            assert len(user_records) == 1
            assert user_records[0]["is_positive"] is False

    def test_low_satisfaction_answers(self):
        with patch("bot.feedback.FEEDBACK_FILE", self.feedback_file):
            from bot.feedback import record_feedback, low_satisfaction_answers
            record_feedback(1, 100, 200, "bad q", "bad a", False)
            record_feedback(2, 100, 201, "good q", "good a", True)
            negatives = low_satisfaction_answers(10)
            assert len(negatives) == 1
            assert negatives[0]["question"] == "bad q"


# ---------------------------------------------------------------------------
# Feature 5: Scheduled reminders
# ---------------------------------------------------------------------------

class TestReminders:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.reminders_file = os.path.join(self.tmpdir, "reminders.json")

    def teardown_method(self):
        if os.path.exists(self.reminders_file):
            os.unlink(self.reminders_file)
        os.rmdir(self.tmpdir)

    def test_add_and_list(self):
        with patch("bot.reminders.REMINDERS_FILE", self.reminders_file):
            from bot.reminders import add_reminder, list_reminders
            now = datetime.now(timezone.utc)
            rem = add_reminder("Test", "Hello", now, [123], 456)
            assert rem["title"] == "Test"
            assert rem["id"].startswith("rem_")
            rems = list_reminders()
            assert len(rems) == 1

    def test_cancel_reminder(self):
        with patch("bot.reminders.REMINDERS_FILE", self.reminders_file):
            from bot.reminders import add_reminder, cancel_reminder, list_reminders
            now = datetime.now(timezone.utc)
            rem = add_reminder("Test", "Hello", now, [123], 456)
            assert cancel_reminder(rem["id"]) is True
            assert cancel_reminder("nonexistent") is False
            assert len(list_reminders()) == 0

    def test_get_due_reminders(self):
        with patch("bot.reminders.REMINDERS_FILE", self.reminders_file):
            from bot.reminders import add_reminder, get_due_reminders
            past = datetime.now(timezone.utc) - timedelta(hours=1)
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            add_reminder("Past", "past", past, [123], 456)
            add_reminder("Future", "future", future, [123], 456)
            due = get_due_reminders(datetime.now(timezone.utc))
            assert len(due) == 1
            assert due[0]["title"] == "Past"

    def test_repeat_reminder(self):
        with patch("bot.reminders.REMINDERS_FILE", self.reminders_file):
            from bot.reminders import add_reminder, get_due_reminders
            past = datetime.now(timezone.utc) - timedelta(hours=2)
            add_reminder("Repeat", "hello", past, [123], 456, repeat="hourly")
            now = datetime.now(timezone.utc)
            due = get_due_reminders(now)
            assert len(due) == 1
            # Calling again immediately should not be due yet
            due2 = get_due_reminders(now)
            assert len(due2) == 0


# ---------------------------------------------------------------------------
# Feature 6: VIP role recognition
# ---------------------------------------------------------------------------

class TestVIP:
    def test_is_vip_no_roles_configured(self):
        with patch("bot.listener.VIP_ROLE_IDS", []):
            from bot.listener import MessageListener
            user = MagicMock()
            assert MessageListener._is_vip(user) is False

    def test_is_vip_user_not_member(self):
        with patch("bot.listener.VIP_ROLE_IDS", [111]):
            from bot.listener import MessageListener
            import discord
            user = MagicMock(spec=discord.User)
            assert MessageListener._is_vip(user) is False

    def test_is_vip_member_with_role(self):
        with patch("bot.listener.VIP_ROLE_IDS", [111]):
            from bot.listener import MessageListener
            import discord
            role = MagicMock()
            role.id = 111
            member = MagicMock(spec=discord.Member)
            member.roles = [role]
            assert MessageListener._is_vip(member) is True

    def test_is_vip_member_without_role(self):
        with patch("bot.listener.VIP_ROLE_IDS", [111]):
            from bot.listener import MessageListener
            import discord
            role = MagicMock()
            role.id = 222
            member = MagicMock(spec=discord.Member)
            member.roles = [role]
            assert MessageListener._is_vip(member) is False


# ---------------------------------------------------------------------------
# Feature 7: Keyword monitoring & alerts
# ---------------------------------------------------------------------------

class TestKeywordAlert:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.alerts_file = os.path.join(self.tmpdir, "alerts.json")

    def teardown_method(self):
        if os.path.exists(self.alerts_file):
            os.unlink(self.alerts_file)
        os.rmdir(self.tmpdir)

    def test_add_and_get_keywords(self):
        with patch("bot.keyword_alert.ALERTS_FILE", self.alerts_file), \
             patch("bot.keyword_alert._cache", None):
            from bot.keyword_alert import add_keyword, get_keywords
            assert add_keyword("crash") is True
            assert add_keyword("crash") is False  # duplicate
            kws = get_keywords()
            assert "crash" in kws

    def test_remove_keyword(self):
        with patch("bot.keyword_alert.ALERTS_FILE", self.alerts_file), \
             patch("bot.keyword_alert._cache", None):
            from bot.keyword_alert import add_keyword, remove_keyword, get_keywords
            add_keyword("crash")
            assert remove_keyword("crash") is True
            assert remove_keyword("crash") is False
            assert len(get_keywords()) == 0

    def test_check_message(self):
        with patch("bot.keyword_alert.ALERTS_FILE", self.alerts_file), \
             patch("bot.keyword_alert._cache", None):
            from bot.keyword_alert import add_keyword, check_message
            add_keyword("crash")
            add_keyword("dump")
            assert check_message("The market is going to crash!") == ["crash"]
            assert check_message("Nothing special") == []
            assert set(check_message("crash and dump")) == {"crash", "dump"}

    def test_check_empty_message(self):
        from bot.keyword_alert import check_message
        assert check_message("") == []
        assert check_message(None) == []


# ---------------------------------------------------------------------------
# Feature 8: KB version management
# ---------------------------------------------------------------------------

class TestKBVersioning:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_create_snapshot(self):
        with patch("bot.kb_versioning.KB_SNAPSHOTS_DIR", self.tmpdir):
            from bot.kb_versioning import create_snapshot, list_snapshots
            snap = create_snapshot(100, "test snapshot")
            assert snap["doc_count"] == 100
            assert snap["id"].startswith("snap_")
            snaps = list_snapshots()
            assert len(snaps) == 1

    def test_snapshot_limit(self):
        with patch("bot.kb_versioning.KB_SNAPSHOTS_DIR", self.tmpdir), \
             patch("bot.kb_versioning._MAX_SNAPSHOTS", 3):
            from bot.kb_versioning import create_snapshot, list_snapshots
            for i in range(5):
                create_snapshot(i * 10, f"snap {i}")
                time.sleep(0.01)
            snaps = list_snapshots()
            assert len(snaps) <= 3

    def test_get_snapshot(self):
        with patch("bot.kb_versioning.KB_SNAPSHOTS_DIR", self.tmpdir):
            from bot.kb_versioning import create_snapshot, get_snapshot
            snap = create_snapshot(50)
            found = get_snapshot(snap["id"])
            assert found is not None
            assert found["doc_count"] == 50
            assert get_snapshot("nonexistent") is None

    def test_delete_old_snapshots(self):
        with patch("bot.kb_versioning.KB_SNAPSHOTS_DIR", self.tmpdir):
            from bot.kb_versioning import create_snapshot, delete_old_snapshots, list_snapshots
            for i in range(5):
                create_snapshot(i * 10)
                time.sleep(0.01)
            deleted = delete_old_snapshots(2)
            assert deleted == 3
            assert len(list_snapshots()) == 2


# ---------------------------------------------------------------------------
# Feature 9: Enhanced welcome flow
# ---------------------------------------------------------------------------

class TestWelcomeFlow:
    @pytest.mark.asyncio
    async def test_welcome_flow_sends_step1_and_schedules_drip(self, tmp_path):
        drip_file = tmp_path / "drip.json"
        funnel_file = tmp_path / "funnel.json"
        with patch("bot.acquisition.DRIP_FILE", str(drip_file)), \
             patch("bot.acquisition.FUNNEL_FILE", str(funnel_file)), \
             patch("bot.welcome_flow.SIGNAL_PRODUCT_NAME", "TestProduct"):
            from bot.welcome_flow import run_welcome_flow
            member = MagicMock()
            member.id = 111
            member.guild.id = 222
            member.guild.name = "TestGuild"
            member.send = AsyncMock()
            await run_welcome_flow(member)
            assert member.send.call_count == 1
            from bot.acquisition import _load_drip
            jobs = _load_drip()
            assert len(jobs) == 3
            assert {j["step"] for j in jobs} == {"value", "cta", "reminder"}

    @pytest.mark.asyncio
    async def test_welcome_flow_includes_notify_buttons(self, tmp_path):
        drip_file = tmp_path / "drip.json"
        funnel_file = tmp_path / "funnel.json"
        with patch("bot.acquisition.DRIP_FILE", str(drip_file)), \
             patch("bot.acquisition.FUNNEL_FILE", str(funnel_file)), \
             patch("bot.role_dm.PROMO_NOTIFY_ROLE_IDS", [111]):
            from bot.welcome_flow import run_welcome_flow
            member = MagicMock()
            member.id = 111
            member.guild.id = 222
            member.guild.name = "TestGuild"
            member.send = AsyncMock()
            await run_welcome_flow(member)
            kwargs = member.send.await_args.kwargs
            embed = kwargs["embed"]
            view = kwargs["view"]
            assert "领取通知" in embed.description
            labels = [c.label for c in view.children]
            assert "领取通知" in labels
            assert "取消订阅" in labels

    @pytest.mark.asyncio
    async def test_welcome_flow_dm_forbidden(self, tmp_path):
        import discord
        drip_file = tmp_path / "drip.json"
        funnel_file = tmp_path / "funnel.json"
        with patch("bot.acquisition.DRIP_FILE", str(drip_file)), \
             patch("bot.acquisition.FUNNEL_FILE", str(funnel_file)):
            from bot.welcome_flow import run_welcome_flow
            member = MagicMock()
            member.id = 111
            member.guild.id = 222
            member.guild.name = "TestGuild"
            member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "DMs disabled"))
            await run_welcome_flow(member)
            from bot.acquisition import _load_drip
            assert _load_drip() == []


# ---------------------------------------------------------------------------
# Feature 10: Leaderboard
# ---------------------------------------------------------------------------

class TestLeaderboard:
    def test_top_questioners(self):
        from bot.leaderboard import top_questioners
        # Returns list; may be empty if no stats
        result = top_questioners(5, 30)
        assert isinstance(result, list)

    def test_top_questions_by_frequency(self):
        from bot.leaderboard import top_questions_by_frequency
        result = top_questions_by_frequency(5, 30)
        assert isinstance(result, list)

    def test_confidence_distribution(self):
        from bot.leaderboard import confidence_distribution
        dist = confidence_distribution(30)
        assert isinstance(dist, dict)
        assert "1-3" in dist
        assert "9-10" in dist

    def test_days_to_range(self):
        from bot.leaderboard import _days_to_range
        assert _days_to_range(1) == "24h"
        assert _days_to_range(7) == "7d"
        assert _days_to_range(30) == "30d"
        assert _days_to_range(90) == "90d"
        assert _days_to_range(365) == "365d"
        assert _days_to_range(999) == "all"


# ---------------------------------------------------------------------------
# Feature 11: A/B test reply styles
# ---------------------------------------------------------------------------

class TestABTest:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.results_file = os.path.join(self.tmpdir, "ab_results.json")

    def teardown_method(self):
        if os.path.exists(self.results_file):
            os.unlink(self.results_file)
        os.rmdir(self.tmpdir)

    def test_pick_variant_disabled(self):
        with patch("bot.ab_test.AB_TEST_ENABLED", False):
            from bot.ab_test import pick_variant
            assert pick_variant() is None

    def test_pick_variant_enabled(self):
        with patch("bot.ab_test.AB_TEST_ENABLED", True), \
             patch("bot.ab_test._VARIANTS", [("casual", "style_a.txt"), ("formal", "style_b.txt")]):
            from bot.ab_test import pick_variant
            result = pick_variant()
            assert result in ("casual", "formal")

    def test_record_and_get_results(self):
        with patch("bot.ab_test.AB_RESULTS_FILE", self.results_file):
            from bot.ab_test import record_result, get_results
            record_result("casual", True)
            record_result("casual", True)
            record_result("casual", False)
            record_result("formal", True)
            results = get_results()
            assert results["casual"]["total"] == 3
            assert results["casual"]["positive"] == 2
            assert results["casual"]["negative"] == 1
            assert results["formal"]["total"] == 1

    def test_get_variants_empty(self):
        with patch("bot.ab_test._VARIANTS", []):
            from bot.ab_test import get_variants
            assert get_variants() == []


# ---------------------------------------------------------------------------
# Feature 12: Export conversations
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_json(self):
        from bot.export import export_json
        result = export_json(30)
        assert isinstance(result, str)
        data = json.loads(result)
        assert isinstance(data, list)

    def test_export_csv(self):
        from bot.export import export_csv
        result = export_csv(30)
        assert isinstance(result, str)
        assert "timestamp" in result  # header row

    def test_export_count(self):
        from bot.export import export_count
        count = export_count(30)
        assert isinstance(count, int)
        assert count >= 0

    def test_days_to_range(self):
        from bot.export import _days_to_range
        assert _days_to_range(1) == "24h"
        assert _days_to_range(7) == "7d"
        assert _days_to_range(30) == "30d"


# ---------------------------------------------------------------------------
# Feature 4: Conversation summary (pin_summary uses LLM — test the flow)
# ---------------------------------------------------------------------------

class TestPinSummary:
    """pin_summary is a slash command; test the summary generation approach."""

    @pytest.mark.asyncio
    async def test_openai_chat_with_retry_success(self):
        from bot.rag import _openai_chat_with_retry
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test summary"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await _openai_chat_with_retry(
            mock_client,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "test"}],
        )
        assert result == "Test summary"


# ---------------------------------------------------------------------------
# Config: new config vars exist
# ---------------------------------------------------------------------------

class TestNewConfig:
    def test_vip_role_ids_exists(self):
        from bot.config import VIP_ROLE_IDS
        assert isinstance(VIP_ROLE_IDS, list)

    def test_feedback_enabled_exists(self):
        from bot.config import FEEDBACK_ENABLED
        assert isinstance(FEEDBACK_ENABLED, bool)

    def test_welcome_flow_enabled_exists(self):
        from bot.config import WELCOME_FLOW_ENABLED
        assert isinstance(WELCOME_FLOW_ENABLED, bool)

    def test_auto_lang_detect_exists(self):
        from bot.config import AUTO_LANG_DETECT
        assert isinstance(AUTO_LANG_DETECT, bool)

    def test_keyword_alert_enabled_exists(self):
        from bot.config import KEYWORD_ALERT_ENABLED
        assert isinstance(KEYWORD_ALERT_ENABLED, bool)
