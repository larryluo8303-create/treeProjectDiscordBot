"""Tests for the confidence routing module."""

from bot.confidence import is_fallback_answer, is_signal_query, parse_confidence, route_answer


class TestParseConfidence:
    def test_parses_normal(self):
        assert parse_confidence("Some answer\nCONFIDENCE: 8") == 8

    def test_parses_lowercase(self):
        assert parse_confidence("Answer\nconfidence: 6") == 6

    def test_clamps_high(self):
        assert parse_confidence("CONFIDENCE: 15") == 10

    def test_clamps_low(self):
        assert parse_confidence("CONFIDENCE: 0") == 1

    def test_missing_returns_default(self):
        assert parse_confidence("Just an answer with no score") == 3


class TestRouteAnswer:
    def test_auto_reply_above_threshold(self):
        result = route_answer(
            answer="AAPL looks good",
            confidence=8,
            threshold=7,
            context_count=5,
            best_distance=0.3,
        )
        assert result["action"] == "auto_reply"

    def test_forward_below_threshold(self):
        result = route_answer(
            answer="Not sure about this",
            confidence=4,
            threshold=7,
            context_count=5,
            best_distance=0.3,
        )
        assert result["action"] == "forward_to_owner"

    def test_forward_no_context(self):
        result = route_answer(
            answer="Some answer",
            confidence=9,
            context_count=0,
            best_distance=1.0,
        )
        assert result["action"] == "forward_to_owner"
        assert "no relevant context" in result["reason"]

    def test_forward_high_distance(self):
        result = route_answer(
            answer="Some answer",
            confidence=9,
            context_count=3,
            best_distance=0.98,
        )
        assert result["action"] == "forward_to_owner"
        assert "distance" in result["reason"]


class TestIsSignalQuery:
    def test_buy_signal_simplified(self):
        assert is_signal_query("现在有买信号吗？")

    def test_buy_signal_traditional(self):
        assert is_signal_query("有買信號嗎")

    def test_sell_signal(self):
        assert is_signal_query("有没有卖信号")

    def test_generic_signal(self):
        assert is_signal_query("现在有信号吗")

    def test_can_i_buy_now(self):
        assert is_signal_query("现在能买吗")

    def test_should_i_sell(self):
        assert is_signal_query("现在该卖吗")

    def test_entry_point(self):
        assert is_signal_query("这里是买点吗")

    def test_short_signal_traditional(self):
        assert is_signal_query("是否可以做空")

    def test_break_out_signal(self):
        assert is_signal_query("突破信号出现了吗")

    def test_non_signal_question(self):
        assert not is_signal_query("你怎么看AAPL")

    def test_general_analysis(self):
        assert not is_signal_query("请分析下大盘走势")

    def test_empty(self):
        assert not is_signal_query("")


class TestIsFallbackAnswer:
    def test_standard_fallback_simplified(self):
        assert is_fallback_answer("这个我不太确定，等频道主来回答")

    def test_standard_fallback_traditional(self):
        assert is_fallback_answer("不確定，頻道主會回答")

    def test_long_answer_not_fallback(self):
        # Even if it mentions 频道主, long answers are not treated as fallback
        text = "这是一个很长的回答" * 20 + "频道主"
        assert not is_fallback_answer(text)

    def test_empty_not_fallback(self):
        assert not is_fallback_answer("")

    def test_none_not_fallback(self):
        assert not is_fallback_answer(None)

    def test_normal_answer_not_fallback(self):
        assert not is_fallback_answer("AAPL目前处于上升趋势")

    def test_short_answer_without_keywords(self):
        assert not is_fallback_answer("不确定")


class TestRouteAnswerSignalQuery:
    def test_signal_query_forced_to_review(self):
        # Even with high confidence, good context, and short distance —
        # signal questions must go to owner.
        result = route_answer(
            answer="现在可以买入",
            confidence=10,
            threshold=7,
            context_count=8,
            best_distance=0.2,
            question="现在有买信号吗？",
        )
        assert result["action"] == "forward_to_owner"
        assert "signal" in result["reason"].lower()

    def test_signal_query_traditional_forced_to_review(self):
        result = route_answer(
            answer="可以做多",
            confidence=9,
            threshold=7,
            context_count=5,
            best_distance=0.3,
            question="有買信號嗎",
        )
        assert result["action"] == "forward_to_owner"

    def test_non_signal_question_unaffected(self):
        result = route_answer(
            answer="AAPL基本面稳健",
            confidence=8,
            threshold=7,
            context_count=5,
            best_distance=0.3,
            question="你怎么看AAPL",
        )
        assert result["action"] == "auto_reply"

    def test_fallback_answer_auto_replies(self):
        """Fallback 'I don't know' answers are safe to auto-post, even below threshold."""
        result = route_answer(
            answer="不太确定，等频道主来回答",
            confidence=2,
            threshold=7,
            context_count=3,
            best_distance=0.4,
            question="SPY怎么看",
        )
        assert result["action"] == "auto_reply"
        assert "fallback" in result["reason"]
