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

    def test_year_range_preserved(self):
        text = "2020-2024年这段时间"
        result, _ = _redact_price_levels(text)
        assert "2020-2024年" in result

    def test_iso_date_preserved(self):
        text = "数据截至2024-01-15"
        result, _ = _redact_price_levels(text)
        assert "2024-01-15" in result

    def test_year_month_preserved(self):
        text = "在2024年3月见顶"
        result, _ = _redact_price_levels(text)
        assert "2024年3月" in result

    def test_month_day_preserved(self):
        text = "3月15日公布"
        result, _ = _redact_price_levels(text)
        assert "3月15日" in result

    def test_year_with_price_still_redacted(self):
        # Year survives, but a real price level in the same sentence is still cut.
        text = "2024年跌破3912"
        result, hits = _redact_price_levels(text)
        assert "2024年" in result
        assert "3912" not in result
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


def _make_429_error():
    """Build an openai.RateLimitError without a real HTTP response."""
    import openai

    resp = MagicMock()
    resp.headers = {}
    return openai.RateLimitError("rate limited", response=resp, body=None)


def _make_auth_error():
    import openai

    resp = MagicMock()
    resp.headers = {}
    return openai.AuthenticationError("invalid key", response=resp, body=None)


def _ok_chat_response(text="ok answer"):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = text
    return mock_response


class TestOpenAI429Retry:
    """429 rate limits: backoff retry, then OpenAIUnavailableError; auth errors fail fast."""

    @pytest.mark.asyncio
    async def test_429_retry_then_success(self):
        from bot.rag import _openai_chat_with_retry

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = [
            _make_429_error(),
            _ok_chat_response("recovered"),
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _openai_chat_with_retry(
                mock_client, model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert result == "recovered"
        assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_429_exhausted_raises_unavailable(self):
        from bot.rag import OpenAIUnavailableError, _openai_chat_with_retry

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = _make_429_error()
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OpenAIUnavailableError):
                await _openai_chat_with_retry(
                    mock_client, model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "hi"}],
                )
        # initial attempt + 3 backoff retries
        assert mock_client.chat.completions.create.call_count == 4

    @pytest.mark.asyncio
    async def test_auth_error_raises_unavailable_immediately(self):
        from bot.rag import OpenAIUnavailableError, _openai_chat_with_retry

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = _make_auth_error()
        with pytest.raises(OpenAIUnavailableError):
            await _openai_chat_with_retry(
                mock_client, model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_embedding_429_retry_then_success(self):
        from bot.rag import _embedding_with_retry

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1, 0.2]
        mock_client.embeddings.create.side_effect = [
            _make_429_error(),
            mock_response,
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _embedding_with_retry(mock_client, "hello")
        assert result == [0.1, 0.2]
        assert mock_client.embeddings.create.call_count == 2


class TestOpenAIDegrade:
    """OpenAIUnavailableError must degrade to a user-facing message, never a silent drop."""

    @pytest.mark.asyncio
    async def test_generate_answer_degrades_to_no_answer(self):
        from bot.config import get_locale
        from bot.rag import OpenAIUnavailableError, generate_answer

        mock_client = AsyncMock()
        with patch(
            "bot.rag._openai_chat_with_retry",
            new=AsyncMock(side_effect=OpenAIUnavailableError("429")),
        ):
            answer, confidence = await generate_answer(
                "test?", [], mock_client
            )
        assert answer == get_locale("no_answer")
        assert confidence == 1

    @pytest.mark.asyncio
    async def test_run_rag_pipeline_degrades_on_embedding_failure(self):
        from bot.config import get_locale
        from bot.rag import OpenAIUnavailableError, run_rag_pipeline

        mock_client = AsyncMock()
        mock_collection = MagicMock()
        with patch(
            "bot.rag.retrieve_context",
            new=AsyncMock(side_effect=OpenAIUnavailableError("quota")),
        ):
            answer, confidence, chunks = await run_rag_pipeline(
                "test?", mock_collection, mock_client
            )
        assert answer == get_locale("no_answer")
        assert confidence == 1
        assert chunks == []


class TestRelaxedOwnKnowledge:
    """2026-09-28 user-approved rule: when the KB has no coverage,
    - signal questions stay KB-only (fallback -> owner review),
    - general questions may be answered from the model's own knowledge
      with a disclaimer (confidence capped at 6, always owner-reviewed).
    """

    @pytest.mark.asyncio
    async def test_empty_context_signal_query_stays_fallback(self):
        from bot.rag import run_rag_pipeline

        mock_client = AsyncMock()
        mock_collection = MagicMock()
        with patch("bot.rag.retrieve_context", new=AsyncMock(return_value=[])):
            answer, confidence, chunks = await run_rag_pipeline(
                "MU现在有买信号吗？", mock_collection, mock_client
            )
        assert chunks == []
        assert confidence == 1
        assert "不太确定" in answer  # fallback, not an own-knowledge analysis

    @pytest.mark.asyncio
    async def test_empty_context_general_query_uses_own_knowledge(self):
        from bot.rag import OWN_KNOWLEDGE_DISCLAIMER, run_rag_pipeline

        mock_client = AsyncMock()
        mock_collection = MagicMock()
        fake_llm = "MU是美光科技，存储芯片龙头。\nCONFIDENCE: 5"
        with (
            patch("bot.rag.retrieve_context", new=AsyncMock(return_value=[])),
            patch("bot.rag._openai_chat_with_retry", new=AsyncMock(return_value=fake_llm)),
        ):
            answer, confidence, chunks = await run_rag_pipeline(
                "分析一下MU", mock_collection, mock_client
            )
        assert chunks == []
        assert "美光" in answer
        assert "不太确定" not in answer
        assert OWN_KNOWLEDGE_DISCLAIMER in answer  # code-enforced disclaimer
        assert confidence == 5

    @pytest.mark.asyncio
    async def test_relaxed_prompt_does_not_leak_into_normal_generation(self):
        """Normal (KB-backed) generation must not get the relaxed section."""
        from bot.rag import RELAXED_KNOWLEDGE_PROMPT, generate_answer

        captured = {}

        async def fake_chat(client, model, messages):
            captured["system"] = messages[0]["content"]
            return "答案\nCONFIDENCE: 8"

        mock_client = AsyncMock()
        with patch("bot.rag._openai_chat_with_retry", new=fake_chat):
            answer, _ = await generate_answer(
                "分析一下MU", [{"text": "x", "distance": 0.3}], mock_client
            )
        assert RELAXED_KNOWLEDGE_PROMPT not in captured["system"]
        assert answer == "答案"

    @pytest.mark.asyncio
    async def test_relaxed_answer_routes_to_owner_review(self):
        """Own-knowledge answers (context_count=0) must go to owner review,
        never auto-reply — this is the guard against hallucination."""
        from bot.confidence import route_answer

        routing = route_answer(
            "MU是美光科技……以上分析基于公开信息，仅供参考，不构成投资建议。",
            5,
            context_count=0,
            best_distance=1.0,
            question="分析一下MU",
        )
        assert routing["action"] == "forward_to_owner"

    def test_signal_fallback_routes_to_owner_review(self):
        """Signal question with no KB coverage: fallback still goes to the
        owner for approval (signal branch fires before the fallback branch)."""
        from bot.confidence import route_answer

        routing = route_answer(
            "这个我不太确定，等频道主来回答",
            1,
            context_count=0,
            best_distance=1.0,
            question="MU现在有买信号吗？",
        )
        assert routing["action"] == "forward_to_owner"
