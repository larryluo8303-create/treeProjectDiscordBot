"""Tests for newly added enhancement modules."""

import tempfile
import time
from unittest.mock import patch

import pytest

from bot.clarification import (
    build_clarification_question,
    build_clarification_reply,
    needs_clarification,
)
from bot.feature_flags import is_feature_enabled_for_channel
from bot.guardrails import detect_high_risk_signals
from bot.reliability import openai_error_rate, p95_latency_ms, record_openai_call, sla_latencies
from bot.session_summary import summarize_memory_entries


class TestFeatureFlags:
    def test_disabled_feature(self):
        assert is_feature_enabled_for_channel(False, [], 123) is False

    def test_enabled_global(self):
        assert is_feature_enabled_for_channel(True, [], 123) is True

    def test_enabled_canary_hit(self):
        assert is_feature_enabled_for_channel(True, [123, 456], 123) is True

    def test_enabled_canary_miss(self):
        assert is_feature_enabled_for_channel(True, [123, 456], 999) is False


class TestClarification:
    def test_needs_clarification_true(self):
        assert needs_clarification(6, 6) is True

    def test_needs_clarification_at_boundary(self):
        # With default CLARIFICATION_CONFIDENCE_MAX = CONFIDENCE_THRESHOLD - 1 (= 6),
        # confidence 7 (auto-reply threshold) should NOT trigger clarification.
        assert needs_clarification(7, 6) is False

    def test_needs_clarification_false(self):
        assert needs_clarification(8, 6) is False

    def test_needs_clarification_low(self):
        assert needs_clarification(5, 6) is True

    def test_build_question_ticker(self):
        q = build_clarification_question("Should I buy AAPL now?")
        assert "AAPL" in q

    def test_build_reply(self):
        text = build_clarification_reply("怎么看TSLA")
        assert "确认" in text


class TestSessionSummary:
    def test_summary_from_entries(self):
        now = time.time()
        entries = [
            (now - 10, "user", "我想看日内交易机会"),
            (now - 8, "bot", "可以先看趋势"),
            (now - 6, "user", "也想控制回撤"),
        ]
        summary = summarize_memory_entries(entries)
        assert "历史会话摘要" in summary
        assert "日内" in summary


class TestGuardrails:
    def test_detects_all_in(self):
        hits = detect_high_risk_signals("", "建议all-in")
        assert len(hits) > 0

    def test_detects_guarantee(self):
        hits = detect_high_risk_signals("保证收益吗", "")
        assert len(hits) > 0

    def test_safe_text(self):
        hits = detect_high_risk_signals("怎么看趋势", "建议观察结构")
        assert hits == []


class TestFeedbackLearning:
    def test_record_and_top_gaps(self):
        from bot import feedback_learning as fl

        with tempfile.TemporaryDirectory() as d:
            queue_file = f"{d}/queue.json"
            state_file = f"{d}/state.json"
            with patch.object(fl, "LEARNING_QUEUE_FILE", queue_file), patch.object(fl, "LEARNING_REPORT_STATE_FILE", state_file):
                fl.record_gap_question("TSLA怎么做", "thumbs_down_feedback")
                fl.record_gap_question("TSLA怎么做", "owner_edited_reply")
                fl.record_gap_question("AAPL怎么做", "thumbs_down_feedback")
                top = fl.top_gap_questions(days=1, limit=10)
                assert len(top) >= 2
                assert top[0]["count"] >= top[1]["count"]

    def test_daily_report_once_per_day(self):
        from bot import feedback_learning as fl

        with tempfile.TemporaryDirectory() as d:
            state_file = f"{d}/state.json"
            with patch.object(fl, "LEARNING_REPORT_STATE_FILE", state_file):
                now = time.time()
                assert fl.should_emit_daily_report(now) is True
                assert fl.should_emit_daily_report(now + 10) is False


class TestReliabilityHelpers:
    def test_p95_latency(self):
        assert p95_latency_ms([100, 200, 300, 400, 500]) >= 400

    def test_p95_single_element(self):
        # Regression B3: single element must return that element, not crash
        assert p95_latency_ms([42]) == 42

    def test_p95_two_elements(self):
        assert p95_latency_ms([100, 900]) == 900

    def test_p95_twenty_elements(self):
        vals = list(range(1, 21))  # 1..20
        result = p95_latency_ms(vals)
        assert result == 19 or result == 20  # 95th percentile of 1..20

    def test_sla_latencies_drops_old_zero_and_hang_samples(self):
        now = time.time()

        class Rec:
            def __init__(self, latency_ms, timestamp):
                self.latency_ms = latency_ms
                self.timestamp = timestamp

        records = [
            Rec(8833, now - 10 * 3600),       # too old
            Rec(0, now - 10),                 # client_auto
            Rec(8_187_336, now - 10),         # hang/restart outlier
            Rec(3402, now - 10),              # valid
            Rec(10160, now - 10),             # valid slow
        ]
        samples = sla_latencies(records, now=now, window_seconds=3600, max_sample_ms=60_000)
        assert samples == [3402, 10160]

    def test_openai_error_rate(self):
        from bot.reliability import reset_openai_calls

        reset_openai_calls()
        record_openai_call(True)
        record_openai_call(False)
        rate = openai_error_rate(window_seconds=3600)
        assert rate == 0.5

    def test_openai_error_rate_empty(self):
        from bot.reliability import reset_openai_calls

        reset_openai_calls()
        assert openai_error_rate() == 0.0

    def test_openai_call_count(self):
        from bot.reliability import openai_call_count, reset_openai_calls

        reset_openai_calls()
        record_openai_call(True)
        record_openai_call(True)
        record_openai_call(False)
        assert openai_call_count() == 3


class TestSlaEvaluate:
    @pytest.mark.asyncio
    async def test_small_sample_openai_errors_do_not_alert(self):
        """3 calls with 1 failure is 33% but must not alert below min sample."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from bot.reliability import (
            evaluate_and_alert,
            mark_scheduler_tick,
            record_openai_call,
            reset_alert_state,
            reset_openai_calls,
        )

        reset_openai_calls()
        reset_alert_state()
        mark_scheduler_tick()
        record_openai_call(True)
        record_openai_call(True)
        record_openai_call(False)

        mock_stats = MagicMock()
        mock_stats.recent = []
        mock_bot = MagicMock()
        mock_bot.fetch_user = AsyncMock()

        mock_queue = MagicMock()
        mock_queue.expire_stale.return_value = 0
        mock_queue.pending_count = 0

        with patch("bot.review_queue.review_queue", mock_queue):
            await evaluate_and_alert(mock_bot, mock_stats)

        mock_bot.fetch_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_stale_backlog_is_expired_before_alert(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from bot.reliability import (
            evaluate_and_alert,
            mark_scheduler_tick,
            reset_alert_state,
            reset_openai_calls,
        )

        reset_openai_calls()
        reset_alert_state()
        mark_scheduler_tick()

        mock_stats = MagicMock()
        mock_stats.recent = []
        mock_bot = MagicMock()
        mock_bot.fetch_user = AsyncMock()

        mock_queue = MagicMock()
        mock_queue.expire_stale.return_value = 21
        mock_queue.pending_count = 0

        with patch("bot.review_queue.review_queue", mock_queue):
            await evaluate_and_alert(mock_bot, mock_stats)

        mock_queue.expire_stale.assert_called_once()
        mock_bot.fetch_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_historical_p95_does_not_alert(self):
        """A day-old 8833ms sample plus a hang outlier must not page."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from bot.reliability import (
            evaluate_and_alert,
            mark_scheduler_tick,
            reset_alert_state,
            reset_openai_calls,
        )

        reset_openai_calls()
        reset_alert_state()
        mark_scheduler_tick()

        now = time.time()

        class Rec:
            def __init__(self, latency_ms, timestamp):
                self.latency_ms = latency_ms
                self.timestamp = timestamp

        mock_stats = MagicMock()
        mock_stats.recent = [
            Rec(8833, now - 86400),
            Rec(8_187_336, now - 100),
            Rec(3402, now - 10),
        ]
        mock_bot = MagicMock()
        mock_queue = MagicMock()
        mock_queue.expire_stale.return_value = 0
        mock_queue.pending_count = 0
        webhook = MagicMock()
        webhook.send_alert = AsyncMock()

        with patch("bot.review_queue.review_queue", mock_queue):
            await evaluate_and_alert(mock_bot, mock_stats, webhook_server=webhook)

        webhook.send_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_p95_alert_is_not_resent(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from bot.reliability import (
            evaluate_and_alert,
            mark_scheduler_tick,
            reset_alert_state,
            reset_openai_calls,
        )

        reset_openai_calls()
        reset_alert_state()
        mark_scheduler_tick()

        now = time.time()

        class Rec:
            def __init__(self, latency_ms, timestamp):
                self.latency_ms = latency_ms
                self.timestamp = timestamp

        mock_stats = MagicMock()
        mock_stats.recent = [Rec(9000, now - 10) for _ in range(8)]
        mock_bot = MagicMock()
        mock_queue = MagicMock()
        mock_queue.expire_stale.return_value = 0
        mock_queue.pending_count = 0
        webhook = MagicMock()
        webhook.send_alert = AsyncMock()

        with patch("bot.review_queue.review_queue", mock_queue):
            await evaluate_and_alert(mock_bot, mock_stats, webhook_server=webhook)
            await evaluate_and_alert(mock_bot, mock_stats, webhook_server=webhook)

        assert webhook.send_alert.await_count == 1


class TestSessionSummaryRecompression:
    """Regression test for B4: summary should not be re-compressed."""

    def test_no_recompression_when_summary_exists(self):
        """Once a summary entry exists in the buffer, adding more messages
        should not trigger a second compression pass."""
        import types
        from unittest.mock import MagicMock, patch
        from bot.listener import MessageListener

        bot = MagicMock()
        bot.user = None
        collection = MagicMock()
        openai_client = MagicMock()
        listener = MessageListener(bot, collection, openai_client)

        ch_id = 99999
        now = time.time()

        # Seed buffer with a summary + several recent entries
        buf = [(now - 100, "summary", "历史会话摘要：用户关注波段操作")]
        for i in range(8):
            buf.append((now - 50 + i, "user", f"msg {i}"))
        listener._channel_memory[ch_id] = buf

        with patch("bot.listener.SESSION_SUMMARY_TRIGGER_MESSAGES", 6), \
             patch("bot.listener.FEATURE_SESSION_SUMMARY", True), \
             patch("bot.listener.FEATURE_SESSION_SUMMARY_CANARY_CHANNEL_IDS", []), \
             patch("bot.listener.CONVERSATION_MEMORY_SIZE", 20), \
             patch("bot.listener.CONVERSATION_MEMORY_TTL", 9999):
            listener._add_to_memory(ch_id, "user", "another question")

        buf = listener._channel_memory[ch_id]
        summary_count = sum(1 for _, r, _ in buf if r == "summary")
        assert summary_count == 1, f"Expected exactly 1 summary entry, got {summary_count}"
