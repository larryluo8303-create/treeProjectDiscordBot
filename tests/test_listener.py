"""Tests for bot.listener filtering and rate-limiting helpers."""

import re
import time
from unittest.mock import MagicMock, patch

from bot.listener import _is_pure_emoji, MessageListener


class TestIsPureEmoji:
    def test_single_emoji(self):
        assert _is_pure_emoji("😀")

    def test_multiple_emojis(self):
        assert _is_pure_emoji("😀🎉🔥")

    def test_text_with_emoji(self):
        assert not _is_pure_emoji("hello 😀")

    def test_plain_text(self):
        assert not _is_pure_emoji("hello world")

    def test_empty_string(self):
        assert not _is_pure_emoji("")

    def test_whitespace(self):
        assert not _is_pure_emoji("   ")

    def test_chinese_characters_not_emoji(self):
        assert not _is_pure_emoji("你好")

    def test_number_not_emoji(self):
        assert not _is_pure_emoji("123")

    def test_flag_emoji(self):
        assert _is_pure_emoji("🇺🇸")


class TestSpamPatterns:
    def test_detects_spam(self):
        assert MessageListener._SPAM_PATTERNS.search("免费开放VIP群组，加入我们")

    def test_detects_telegram_link(self):
        from bot.auto_mod import _EXTERNAL_PLATFORM_LINKS
        assert _EXTERNAL_PLATFORM_LINKS.search("加入 t.me/some_group")

    def test_normal_message_not_spam(self):
        assert not MessageListener._SPAM_PATTERNS.search("你觉得AAPL怎么样？")

    def test_empty_not_spam(self):
        assert not MessageListener._SPAM_PATTERNS.search("")


class TestCourtesyPatterns:
    def test_thanks(self):
        assert MessageListener._COURTESY_PATTERNS.search("谢谢")

    def test_ok_thanks(self):
        assert MessageListener._COURTESY_PATTERNS.search("好的谢谢")

    def test_normal_question_not_courtesy(self):
        assert not MessageListener._COURTESY_PATTERNS.search("AAPL现在能买吗")


class TestQuestionPatterns:
    def test_question_mark(self):
        assert MessageListener._QUESTION_PATTERNS.search("这个股票怎么样？")

    def test_how_to(self):
        assert MessageListener._QUESTION_PATTERNS.search("怎么看这个走势")

    def test_statement(self):
        assert not MessageListener._QUESTION_PATTERNS.search("今天大盘涨了")


class TestTestimonialPatterns:
    def test_profit_simplified(self):
        assert MessageListener._TESTIMONIAL_PATTERNS.search("跟单赚了不少")

    def test_english_gains(self):
        assert MessageListener._TESTIMONIAL_PATTERNS.search("I made some gains today")

    def test_normal_not_testimonial(self):
        assert not MessageListener._TESTIMONIAL_PATTERNS.search("今天天气不错")


class TestRateLimiter:
    """Test the token-bucket rate limiter in MessageListener."""

    def _make_listener(self):
        """Build a minimal MessageListener without a real bot/collection/openai."""
        listener = MessageListener.__new__(MessageListener)
        listener._user_cooldowns = {}
        listener._global_tokens = 10.0
        listener._global_last_refill = time.time()
        return listener

    def test_first_request_allowed(self):
        from unittest.mock import patch
        listener = self._make_listener()
        with patch("bot.listener.USER_COOLDOWN_SECONDS", 30), \
             patch("bot.listener.GLOBAL_MAX_PER_MINUTE", 10):
            assert listener._is_rate_limited(123) is False

    def test_second_request_blocked(self):
        listener = self._make_listener()
        with patch("bot.listener.USER_COOLDOWN_SECONDS", 30), \
             patch("bot.listener.GLOBAL_MAX_PER_MINUTE", 10):
            assert listener._is_rate_limited(123) is False
            listener._record_reply(123)
            assert listener._is_rate_limited(123) is True

    def test_different_users_independent(self):
        from unittest.mock import patch
        listener = self._make_listener()
        with patch("bot.listener.USER_COOLDOWN_SECONDS", 30), \
             patch("bot.listener.GLOBAL_MAX_PER_MINUTE", 10):
            assert listener._is_rate_limited(1) is False
            assert listener._is_rate_limited(2) is False


class TestConversationMemory:
    def _make_listener(self):
        listener = MessageListener.__new__(MessageListener)
        listener._channel_memory = {}
        return listener

    def test_add_and_get(self):
        listener = self._make_listener()
        listener._add_to_memory(100, "user", "hello")
        history = listener._get_memory(100)
        assert len(history) == 1
        assert history[0][0] == "user"
        assert history[0][1] == "hello"

    def test_caps_long_text(self):
        listener = self._make_listener()
        long_text = "x" * 1000
        listener._add_to_memory(100, "user", long_text)
        history = listener._get_memory(100)
        assert len(history[0][1]) == 500  # capped at 500

    def test_format_memory_empty(self):
        listener = self._make_listener()
        assert listener._format_memory(999) == ""

    def test_format_memory_nonempty(self):
        listener = self._make_listener()
        listener._add_to_memory(100, "user", "Question?")
        listener._add_to_memory(100, "bot", "Answer.")
        formatted = listener._format_memory(100)
        assert len(formatted) > 0
        assert "Question?" in formatted
        assert "Answer." in formatted


class TestIsThread:
    def test_regular_channel_not_thread(self):
        channel = MagicMock(spec=[])  # no Thread spec
        assert MessageListener._is_thread(channel) is False

    def test_thread_is_thread(self):
        import discord
        thread = MagicMock(spec=discord.Thread)
        assert MessageListener._is_thread(thread) is True

    def test_get_parent_channel_id_regular(self):
        channel = MagicMock(spec=[])
        channel.id = 123
        assert MessageListener._get_parent_channel_id(channel) == 123

    def test_get_parent_channel_id_thread(self):
        import discord
        thread = MagicMock(spec=discord.Thread)
        thread.parent_id = 456
        thread.id = 789
        assert MessageListener._get_parent_channel_id(thread) == 456


class TestVoiceAttachmentHelpers:
    def _listener(self):
        listener = MessageListener.__new__(MessageListener)
        listener.bot = MagicMock()
        listener.bot.user = MagicMock()
        listener.bot.user.id = 999
        return listener

    def test_detects_discord_voice_message_flag(self):
        att = MagicMock()
        att.is_voice_message = MagicMock(return_value=True)
        att.filename = "clip.ogg"
        att.content_type = "audio/ogg"
        msg = MagicMock()
        msg.attachments = [att]
        assert MessageListener._get_voice_attachment(msg) is att

    def test_detects_voice_message_filename_fallback(self):
        att = MagicMock()
        att.is_voice_message = MagicMock(return_value=False)
        att.filename = "voice-message.ogg"
        att.content_type = "audio/ogg; codecs=opus"
        msg = MagicMock()
        msg.attachments = [att]
        assert MessageListener._get_voice_attachment(msg) is att

    def test_ignores_arbitrary_mp3(self):
        att = MagicMock()
        att.is_voice_message = MagicMock(return_value=False)
        att.filename = "song.mp3"
        att.content_type = "audio/mpeg"
        msg = MagicMock()
        msg.attachments = [att]
        assert MessageListener._get_voice_attachment(msg) is None

    def test_ignores_image_only(self):
        att = MagicMock()
        att.is_voice_message = MagicMock(return_value=False)
        att.filename = "chart.png"
        att.content_type = "image/png"
        msg = MagicMock()
        msg.attachments = [att]
        assert MessageListener._get_voice_attachment(msg) is None

    def test_rejects_oversized_voice(self):
        from bot.listener import _MAX_VOICE_BYTES
        att = MagicMock()
        att.size = _MAX_VOICE_BYTES + 1
        att.duration = 10
        assert MessageListener._voice_reject_reason(att) is not None

    def test_rejects_too_long_duration(self):
        att = MagicMock()
        att.size = 1000
        att.duration = 120
        assert MessageListener._voice_reject_reason(att) is not None

    def test_allows_normal_voice(self):
        att = MagicMock()
        att.size = 50_000
        att.duration = 30
        assert MessageListener._voice_reject_reason(att) is None

    def test_voice_warrants_response(self):
        listener = self._listener()
        msg = MagicMock()
        msg.mentions = []
        msg.reference = None
        msg.content = ""
        assert listener._is_response_warranted(msg, False, has_voice=True) is True

    def test_should_not_skip_voice_only_message(self):
        listener = self._listener()
        msg = MagicMock()
        msg.author.bot = False
        msg.author.id = 12345
        msg.content = ""
        msg.channel.id = 111
        msg.mentions = []
        msg.reference = None
        att = MagicMock()
        att.is_voice_message = MagicMock(return_value=True)
        att.filename = "voice-message.ogg"
        att.content_type = "audio/ogg"
        msg.attachments = [att]

        with patch("bot.listener.OWNER_USER_ID", 1), \
             patch("bot.listener.EXCLUDED_CHANNEL_IDS", []), \
             patch("bot.listener.TARGET_CHANNEL_IDS", []), \
             patch("bot.listener.RESPOND_MODE", "questions"):
            assert listener._should_skip(msg) is False

    def test_transcript_skips_courtesy(self):
        listener = self._listener()
        msg = MagicMock()
        msg.mentions = []
        msg.reference = None
        with patch("bot.listener.RESPOND_MODE", "questions"):
            assert listener._voice_transcript_wants_reply(msg, "好的谢谢") is False

    def test_transcript_keeps_question(self):
        listener = self._listener()
        msg = MagicMock()
        msg.mentions = []
        msg.reference = None
        with patch("bot.listener.RESPOND_MODE", "questions"):
            assert listener._voice_transcript_wants_reply(msg, "TLT现在能买吗？") is True
