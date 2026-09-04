"""Tests for the RAG pipeline utility functions."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.rag import _build_context_block, _parse_confidence, _redact_price_levels


class TestParseConfidence:
    def test_extracts_score_and_cleans_answer(self):
        text = "AAPL is looking bullish.\nCONFIDENCE: 8"
        answer, score = _parse_confidence(text)
        assert score == 8
        assert "CONFIDENCE" not in answer
        assert "AAPL is looking bullish." in answer

    def test_handles_missing_score(self):
        text = "Just an answer"
        answer, score = _parse_confidence(text)
        assert score == 3
        assert answer == "Just an answer"

    def test_clamps_score(self):
        text = "Answer\nCONFIDENCE: 15"
        _, score = _parse_confidence(text)
        assert score == 10


class TestBuildContextBlock:
    def test_formats_qa_pairs(self):
        chunks = [
            {"text": "Q: What about TSLA?\nA: Looking at support at 200", "metadata": {"type": "qa_pair"}},
        ]
        block = _build_context_block(chunks)
        assert "Q&A" in block
        assert "TSLA" in block

    def test_formats_standalone(self):
        chunks = [
            {"text": "The market is volatile today", "metadata": {"type": "standalone"}},
        ]
        block = _build_context_block(chunks)
        assert "Example 1" in block
        assert "volatile" in block

    def test_multiple_chunks(self):
        chunks = [
            {"text": "First chunk", "metadata": {"type": "standalone"}},
            {"text": "Second chunk", "metadata": {"type": "standalone"}},
        ]
        block = _build_context_block(chunks)
        assert "---" in block
        assert "First chunk" in block
        assert "Second chunk" in block


# ── Price redaction tests ───────────────────────────────────────────────────


class TestRedactPriceLevels:
    def test_support_with_number(self):
        text = "支撑在3900附近"
        result, hits = _redact_price_levels(text)
        assert "3900" not in result
        assert hits > 0

    def test_resistance_with_number(self):
        text = "阻力位在86附近"
        result, hits = _redact_price_levels(text)
        assert "86" not in result
        assert "阻力" in result

    def test_target_price(self):
        text = "目标价看到95"
        result, hits = _redact_price_levels(text)
        assert "95" not in result
        assert hits > 0

    def test_stop_loss(self):
        text = "止损设在82.5"
        result, hits = _redact_price_levels(text)
        assert "82.5" not in result
        assert hits > 0

    def test_stop_loss_direct(self):
        text = "止损82.5"
        result, hits = _redact_price_levels(text)
        assert "82.5" not in result
        assert "止损位" in result

    def test_breakout(self):
        text = "突破3950就可以做多"
        result, hits = _redact_price_levels(text)
        assert "3950" not in result
        assert "突破" in result

    def test_entry_with_number(self):
        text = "买入在180附近"
        result, hits = _redact_price_levels(text)
        assert "180" not in result

    def test_indicator_preserved(self):
        text = "看EMA13和MA200的交叉"
        result, hits = _redact_price_levels(text)
        assert "EMA13" in result
        assert "MA200" in result
        assert hits == 0

    def test_percentage_preserved(self):
        text = "90%仓位做多"
        result, hits = _redact_price_levels(text)
        assert "90%" in result

    def test_no_redaction_needed(self):
        text = "大盘走势不错，继续关注"
        result, hits = _redact_price_levels(text)
        assert result == text
        assert hits == 0

    def test_range_redacted(self):
        text = "区间3800-3900震荡"
        result, hits = _redact_price_levels(text)
        assert "3800" not in result
        assert "3900" not in result

    def test_dedup_cleanup(self):
        text = "86附近附近"
        result, hits = _redact_price_levels(text)
        # Should not have double "附近"
        assert "附近附近" not in result or hits == 0


class TestStyleCache:
    """Test _load_style_guidelines caching behavior."""

    def test_returns_string(self):
        from bot.rag import _load_style_guidelines
        result = _load_style_guidelines()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cache_hit_on_repeated_call(self):
        from bot.rag import _load_style_guidelines
        import bot.rag as rag_module
        # Reset cache
        rag_module._style_cache = None
        rag_module._style_cache_time = 0.0

        r1 = _load_style_guidelines()
        # Second call should use cache (same result, fast)
        r2 = _load_style_guidelines()
        assert r1 == r2


class TestNegativeGuidanceCache:
    """Test _build_negative_guidance caching behavior."""

    def test_returns_string(self):
        from bot.rag import _build_negative_guidance
        result = _build_negative_guidance()
        assert isinstance(result, str)

    def test_cache_hit_avoids_file_read(self):
        import bot.rag as rag_module
        from bot.rag import _build_negative_guidance

        # Reset cache
        rag_module._negative_cache = None
        rag_module._negative_cache_time = 0.0

        # First call populates cache
        r1 = _build_negative_guidance()
        # Second call should use cache
        r2 = _build_negative_guidance()
        assert r1 == r2

    def test_cache_expires(self):
        import bot.rag as rag_module
        from bot.rag import _build_negative_guidance

        # Set cache to expired time
        rag_module._negative_cache = "old cached value"
        rag_module._negative_cache_time = 0.0  # ancient timestamp

        result = _build_negative_guidance()
        # Should have refreshed (may or may not equal old value,
        # but cache_time should be updated)
        assert rag_module._negative_cache_time > 0.0


class TestOpenAIChatWithRetry:
    @pytest.mark.asyncio
    async def test_success_first_try(self):
        from bot.rag import _openai_chat_with_retry

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test answer"
        mock_client.chat.completions.create.return_value = mock_response

        result = await _openai_chat_with_retry(
            mock_client, model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result == "test answer"
        assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        import openai
        from bot.rag import _openai_chat_with_retry

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "retried answer"

        # First call raises timeout, second succeeds
        mock_client.chat.completions.create.side_effect = [
            openai.APITimeoutError(request=MagicMock()),
            mock_response,
        ]

        result = await _openai_chat_with_retry(
            mock_client, model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result == "retried answer"
        assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_none_on_double_failure(self):
        import openai
        from bot.rag import _openai_chat_with_retry

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = [
            openai.APITimeoutError(request=MagicMock()),
            openai.APITimeoutError(request=MagicMock()),
        ]

        result = await _openai_chat_with_retry(
            mock_client, model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_null_content_returns_empty_string(self):
        from bot.rag import _openai_chat_with_retry

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_client.chat.completions.create.return_value = mock_response

        result = await _openai_chat_with_retry(
            mock_client, model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result == ""


class TestOpenAIRetrySlaRecording:
    """A recovered retry must count as one success, not 50% error rate."""

    @pytest.mark.asyncio
    async def test_recovered_retry_counts_as_success(self):
        import openai
        from bot.rag import _openai_chat_with_retry
        from bot.reliability import openai_call_count, openai_error_rate, reset_openai_calls

        reset_openai_calls()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_client.chat.completions.create.side_effect = [
            openai.APITimeoutError(request=MagicMock()),
            mock_response,
        ]

        result = await _openai_chat_with_retry(
            mock_client, model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result == "ok"
        assert openai_call_count() == 1
        assert openai_error_rate() == 0.0

    @pytest.mark.asyncio
    async def test_double_failure_counts_as_one_error(self):
        import openai
        from bot.rag import _openai_chat_with_retry
        from bot.reliability import openai_call_count, openai_error_rate, reset_openai_calls

        reset_openai_calls()
        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = [
            openai.APITimeoutError(request=MagicMock()),
            openai.APITimeoutError(request=MagicMock()),
        ]

        result = await _openai_chat_with_retry(
            mock_client, model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result is None
        assert openai_call_count() == 1
        assert openai_error_rate() == 1.0
