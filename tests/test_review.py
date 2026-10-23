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


# ── Persistent review buttons (survive bot restarts) ─────────────────────────


class TestPersistentReviewView:
    def test_view_is_persistent_with_fixed_custom_ids(self):
        from unittest.mock import MagicMock

        from bot.review import ReviewView

        view = ReviewView(MagicMock(), "draft", MagicMock())
        assert view.timeout is None
        custom_ids = {child.custom_id for child in view.children}
        assert custom_ids == {"review:approve", "review:edit", "review:reject"}

    def test_original_message_id_parsed_from_dm_link(self):
        from unittest.mock import MagicMock

        import discord

        from bot.review import _original_message_id_from_dm

        embed = discord.Embed()
        embed.add_field(
            name="Link",
            value="[Jump to message](https://discord.com/channels/895349295975370802/923449257711763466/1563325826798194719)",
            inline=False,
        )
        dm = MagicMock()
        dm.embeds = [embed]
        assert _original_message_id_from_dm(dm) == 1563325826798194719

        dm.embeds = []
        assert _original_message_id_from_dm(dm) is None

    @pytest.mark.asyncio
    async def test_template_resolve_rebuilds_state_from_queue(self):
        """After a restart only the template view exists; a click must
        rebuild the draft + original message from the review queue."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import discord

        from bot.review import ReviewView

        embed = discord.Embed()
        embed.add_field(
            name="Link",
            value="[Jump to message](https://discord.com/channels/1/222/1563325826798194719)",
            inline=False,
        )
        interaction = MagicMock()
        interaction.message.embeds = [embed]

        item = MagicMock()
        item.status = "pending"
        item.channel_id = 222
        item.message_id = 1563325826798194719
        item.draft_answer = "the draft"

        original = MagicMock()
        channel = MagicMock()
        channel.fetch_message = AsyncMock(return_value=original)
        bot = MagicMock()
        bot.get_channel.return_value = channel

        template = ReviewView(None, "", bot)
        with patch("bot.review._find_review_item", return_value=item):
            resolved = await template._resolve(interaction)

        assert resolved is not None
        assert resolved.original_message is original
        assert resolved.draft_answer == "the draft"

    @pytest.mark.asyncio
    async def test_template_resolve_rejects_already_handled(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        import discord

        from bot.review import ReviewView

        embed = discord.Embed()
        embed.add_field(
            name="Link",
            value="[Jump to message](https://discord.com/channels/1/222/1563325826798194719)",
            inline=False,
        )
        interaction = MagicMock()
        interaction.message.embeds = [embed]
        interaction.response.send_message = AsyncMock()

        item = MagicMock()
        item.status = "approved"
        bot = MagicMock()
        template = ReviewView(None, "", bot)
        with patch("bot.review._find_review_item", return_value=item):
            resolved = await template._resolve(interaction)

        assert resolved is None
        interaction.response.send_message.assert_awaited_once()


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
