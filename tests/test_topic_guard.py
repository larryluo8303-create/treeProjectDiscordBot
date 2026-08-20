"""Tests for bot.topic_guard — topic-restricted channel enforcement."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bot.topic_guard as tg
from bot.topic_guard import (
    _cache,
    _cache_get,
    _cache_key,
    _cache_put,
    _is_trivial,
    check_topic,
    classify_message,
    is_topic_restricted,
    set_openai_client,
)


def _reset():
    """Reset module state for test isolation."""
    tg._openai_client = None
    tg._cache.clear()


# ── is_topic_restricted ──────────────────────────────────────────────────

class TestIsTopicRestricted:
    def test_not_restricted(self):
        with patch.object(tg, "_TOPIC_RESTRICTED_SET", {111, 222}):
            assert is_topic_restricted(999) is False

    def test_restricted(self):
        with patch.object(tg, "_TOPIC_RESTRICTED_SET", {111, 222}):
            assert is_topic_restricted(111) is True

    def test_empty_list(self):
        with patch.object(tg, "_TOPIC_RESTRICTED_SET", set()):
            assert is_topic_restricted(111) is False


# ── _is_trivial ──────────────────────────────────────────────────────────

class TestIsTrivial:
    def test_short_message(self):
        assert _is_trivial("hi") == "off_topic"

    def test_single_char(self):
        assert _is_trivial("x") == "off_topic"

    def test_empty_after_strip(self):
        assert _is_trivial("  ") == "off_topic"

    def test_pure_emoji(self):
        assert _is_trivial("😂😂😂") == "off_topic"

    def test_normal_text(self):
        assert _is_trivial("AAPL looks bullish today") is None

    def test_chinese_text(self):
        assert _is_trivial("今天AAPL走势如何") is None

    def test_three_char_text(self):
        assert _is_trivial("buy") is None


# ── Cache ─────────────────────────────────────────────────────────────────

class TestCache:
    def setup_method(self):
        _reset()

    def test_put_and_get(self):
        _cache_put("hello", "on_topic")
        assert _cache_get("hello") == "on_topic"

    def test_miss(self):
        assert _cache_get("nonexistent") is None

    def test_case_insensitive(self):
        _cache_put("Hello World", "off_topic")
        assert _cache_get("hello world") == "off_topic"

    def test_expired(self):
        _cache_put("test", "on_topic")
        key = _cache_key("test")
        # Expire by backdating timestamp
        ts, label = _cache[key]
        _cache[key] = (ts - 999, label)
        assert _cache_get("test") is None

    def test_max_size(self):
        with patch.object(tg, "_CACHE_MAX", 3):
            for i in range(5):
                _cache_put(f"msg_{i}", "on_topic")
            assert len(_cache) == 3


# ── classify_message ──────────────────────────────────────────────────────

class TestClassifyMessage:
    def setup_method(self):
        _reset()

    @pytest.mark.asyncio
    async def test_empty_message(self):
        assert await classify_message("") == "off_topic"

    @pytest.mark.asyncio
    async def test_whitespace_only(self):
        assert await classify_message("   ") == "off_topic"

    @pytest.mark.asyncio
    async def test_trivial_short(self):
        assert await classify_message("ok") == "off_topic"

    @pytest.mark.asyncio
    async def test_no_client_defaults_on_topic(self):
        """Without OpenAI client, non-trivial messages default to on_topic."""
        result = await classify_message("What do you think about AAPL?")
        assert result == "on_topic"

    @pytest.mark.asyncio
    async def test_cached_result(self):
        _cache_put("some trading question", "on_topic")
        result = await classify_message("some trading question")
        assert result == "on_topic"

    @pytest.mark.asyncio
    async def test_gpt_on_topic(self):
        mock_client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "on_topic"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        tg._openai_client = mock_client

        result = await classify_message("AAPL broke resistance at 150")
        assert result == "on_topic"

    @pytest.mark.asyncio
    async def test_gpt_off_topic(self):
        mock_client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "off_topic"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        tg._openai_client = mock_client

        result = await classify_message("今天天气不错哈哈哈")
        assert result == "off_topic"

    @pytest.mark.asyncio
    async def test_gpt_offensive(self):
        mock_client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "offensive"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        tg._openai_client = mock_client

        result = await classify_message("you are an idiot loser!")
        assert result == "offensive"

    @pytest.mark.asyncio
    async def test_gpt_error_defaults_on_topic(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
        tg._openai_client = mock_client

        result = await classify_message("some long message here for testing")
        assert result == "on_topic"

    @pytest.mark.asyncio
    async def test_gpt_result_cached(self):
        mock_client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "off_topic"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        tg._openai_client = mock_client

        await classify_message("some random chatter here")
        # Second call should use cache
        mock_client.chat.completions.create.reset_mock()
        result = await classify_message("some random chatter here")
        assert result == "off_topic"
        mock_client.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_gpt_normalizes_label(self):
        mock_client = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "  OFF_TOPIC  \n"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        tg._openai_client = mock_client

        result = await classify_message("totally unrelated message here")
        assert result == "off_topic"


# ── check_topic ───────────────────────────────────────────────────────────

class TestCheckTopic:
    def setup_method(self):
        _reset()

    @pytest.mark.asyncio
    async def test_non_restricted_channel(self):
        with patch.object(tg, "_TOPIC_RESTRICTED_SET", set()):
            result = await check_topic(123, "random stuff")
            assert result is None

    @pytest.mark.asyncio
    async def test_on_topic_passes(self):
        with patch.object(tg, "_TOPIC_RESTRICTED_SET", {123}):
            _cache_put("AAPL looks bullish", "on_topic")
            result = await check_topic(123, "AAPL looks bullish")
            assert result is None

    @pytest.mark.asyncio
    async def test_off_topic_blocked(self):
        with patch.object(tg, "_TOPIC_RESTRICTED_SET", {123}):
            _cache_put("今天吃什么", "off_topic")
            result = await check_topic(123, "今天吃什么")
            assert result is not None
            assert "off-topic" in result

    @pytest.mark.asyncio
    async def test_offensive_blocked(self):
        with patch.object(tg, "_TOPIC_RESTRICTED_SET", {123}):
            _cache_put("你是白痴", "offensive")
            result = await check_topic(123, "你是白痴")
            assert result is not None
            assert "offensive" in result


# ── set_openai_client ─────────────────────────────────────────────────────

class TestSetClient:
    def setup_method(self):
        _reset()

    def test_set_client(self):
        mock = MagicMock()
        set_openai_client(mock)
        assert tg._openai_client is mock


# ── Config ────────────────────────────────────────────────────────────────

class TestConfig:
    def test_default_empty(self):
        from bot.config import TOPIC_RESTRICTED_CHANNEL_IDS
        # Default env has no value, so it should be an empty list
        assert isinstance(TOPIC_RESTRICTED_CHANNEL_IDS, list)
