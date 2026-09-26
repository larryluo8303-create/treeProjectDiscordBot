"""Tests for bot.review negative sample storage."""

import json
import os
import tempfile

import pytest

import bot.review as review_module


class TestNegativeSamples:
    def test_store_and_load(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        original = review_module.NEGATIVE_SAMPLES_FILE
        review_module.NEGATIVE_SAMPLES_FILE = tmp_path
        try:
            review_module._store_negative_sample("What about AAPL?", "Buy now!")
            samples = review_module.load_negative_samples()
            assert len(samples) == 1
            assert samples[0]["question"] == "What about AAPL?"
            assert samples[0]["bad_answer"] == "Buy now!"
            assert "timestamp" in samples[0]
        finally:
            review_module.NEGATIVE_SAMPLES_FILE = original
            os.unlink(tmp_path)

    def test_max_samples_cap(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        original = review_module.NEGATIVE_SAMPLES_FILE
        original_max = review_module._MAX_NEGATIVE_SAMPLES
        review_module.NEGATIVE_SAMPLES_FILE = tmp_path
        review_module._MAX_NEGATIVE_SAMPLES = 3
        try:
            for i in range(5):
                review_module._store_negative_sample(f"q{i}?", f"a{i}")
            samples = review_module.load_negative_samples()
            assert len(samples) == 3
            # Should keep the latest 3
            assert samples[0]["question"] == "q2?"
            assert samples[2]["question"] == "q4?"
        finally:
            review_module.NEGATIVE_SAMPLES_FILE = original
            review_module._MAX_NEGATIVE_SAMPLES = original_max
            os.unlink(tmp_path)

    def test_empty_question_ignored(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        original = review_module.NEGATIVE_SAMPLES_FILE
        review_module.NEGATIVE_SAMPLES_FILE = tmp_path
        try:
            review_module._store_negative_sample("", "some answer")
            samples = review_module.load_negative_samples()
            assert len(samples) == 0
        finally:
            review_module.NEGATIVE_SAMPLES_FILE = original
            os.unlink(tmp_path)

    def test_load_missing_file(self):
        original = review_module.NEGATIVE_SAMPLES_FILE
        review_module.NEGATIVE_SAMPLES_FILE = "/nonexistent/path.json"
        try:
            samples = review_module.load_negative_samples()
            assert samples == []
        finally:
            review_module.NEGATIVE_SAMPLES_FILE = original


class TestNegativeGuidance:
    def test_build_negative_guidance_with_samples(self):
        import bot.rag as rag_module
        from bot.rag import _build_negative_guidance
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name
            json.dump([
                {"question": "Should I buy?", "bad_answer": "Yes, buy everything!", "timestamp": 1.0}
            ], f)

        original = review_module.NEGATIVE_SAMPLES_FILE
        review_module.NEGATIVE_SAMPLES_FILE = tmp_path
        # Reset the negative guidance cache so it re-reads the file
        rag_module._negative_cache = None
        rag_module._negative_cache_time = 0.0
        try:
            guidance = _build_negative_guidance()
            assert "Should I buy?" in guidance
            assert "Yes, buy everything!" in guidance
        finally:
            review_module.NEGATIVE_SAMPLES_FILE = original
            rag_module._negative_cache = None
            rag_module._negative_cache_time = 0.0
            os.unlink(tmp_path)

    def test_build_negative_guidance_empty(self):
        import bot.rag as rag_module
        from bot.rag import _build_negative_guidance
        original = review_module.NEGATIVE_SAMPLES_FILE
        review_module.NEGATIVE_SAMPLES_FILE = "/nonexistent/path.json"
        # Reset the negative guidance cache
        rag_module._negative_cache = None
        rag_module._negative_cache_time = 0.0
        try:
            guidance = _build_negative_guidance()
            assert guidance == ""
        finally:
            review_module.NEGATIVE_SAMPLES_FILE = original
            rag_module._negative_cache = None
            rag_module._negative_cache_time = 0.0


# ── Review DM owner-fetch fallback ───────────────────────────────────────────


class TestReviewOwnerFallback:
    @pytest.mark.asyncio
    async def test_falsy_owner_still_replies_to_user(self):
        """fetch_user returning None must still send the 中文 fallback reply
        to the original user (same as the exception path)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from bot.review import send_for_review

        bot = MagicMock()
        bot.fetch_user = AsyncMock(return_value=None)
        message = MagicMock()
        message.reply = AsyncMock()
        message.id = 123

        with patch("bot.review.OWNER_USER_ID", 999):
            await send_for_review(bot, message, "draft", 50)

        message.reply.assert_awaited_once()
        args, kwargs = message.reply.await_args
        assert "已记录" in args[0]

    @pytest.mark.asyncio
    async def test_fetch_exception_still_replies_to_user(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from bot.review import send_for_review

        bot = MagicMock()
        bot.fetch_user = AsyncMock(side_effect=RuntimeError("boom"))
        message = MagicMock()
        message.reply = AsyncMock()
        message.id = 123

        with patch("bot.review.OWNER_USER_ID", 999):
            await send_for_review(bot, message, "draft", 50)

        message.reply.assert_awaited_once()
