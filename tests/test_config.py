"""Tests for bot.config module — locale helper and configuration parsing."""

from bot.config import get_locale, LOCALE, BOT_LANGUAGE


class TestGetLocale:
    def test_returns_known_key(self):
        result = get_locale("no_answer")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_key_for_unknown(self):
        result = get_locale("nonexistent_key_xyz")
        # Falls back to returning the key itself if not found in any locale
        assert result == "nonexistent_key_xyz"

    def test_zh_locale_has_required_keys(self):
        required = [
            "rate_limited_user", "rate_limited_global", "no_answer", "unsure",
            "owner_only", "conversation_user", "conversation_bot",
            "conversation_header",
        ]
        for key in required:
            assert key in LOCALE["zh"], f"Missing key '{key}' in zh locale"

    def test_en_locale_has_required_keys(self):
        required = [
            "rate_limited_user", "rate_limited_global", "no_answer", "unsure",
            "owner_only", "conversation_user", "conversation_bot",
            "conversation_header",
        ]
        for key in required:
            assert key in LOCALE["en"], f"Missing key '{key}' in en locale"

    def test_locale_consistency(self):
        """Both locales should have the same set of keys."""
        zh_keys = set(LOCALE["zh"].keys())
        en_keys = set(LOCALE["en"].keys())
        assert zh_keys == en_keys, f"Mismatched keys: zh-only={zh_keys - en_keys}, en-only={en_keys - zh_keys}"


class TestConfigTypes:
    """Sanity check that config values parse to correct types."""

    def test_ints(self):
        from bot.config import (
            RAG_TOP_K, CONFIDENCE_THRESHOLD, LLM_MAX_TOKENS,
            CONVERSATION_MEMORY_SIZE, CONVERSATION_MEMORY_TTL,
            USER_COOLDOWN_SECONDS, GLOBAL_MAX_PER_MINUTE,
            CTA_FREQUENCY,
        )
        for val in [RAG_TOP_K, CONFIDENCE_THRESHOLD, LLM_MAX_TOKENS,
                    CONVERSATION_MEMORY_SIZE, CONVERSATION_MEMORY_TTL,
                    USER_COOLDOWN_SECONDS, GLOBAL_MAX_PER_MINUTE,
                    CTA_FREQUENCY]:
            assert isinstance(val, int)

    def test_floats(self):
        from bot.config import RAG_MAX_DISTANCE, LLM_TEMPERATURE
        assert isinstance(RAG_MAX_DISTANCE, float)
        assert isinstance(LLM_TEMPERATURE, float)

    def test_strings(self):
        from bot.config import LLM_MODEL, EMBEDDING_MODEL, RESPOND_MODE
        assert isinstance(LLM_MODEL, str)
        assert isinstance(EMBEDDING_MODEL, str)
        assert isinstance(RESPOND_MODE, str)

    def test_lists(self):
        from bot.config import TARGET_CHANNEL_IDS, PROMO_CHANNEL_IDS
        assert isinstance(TARGET_CHANNEL_IDS, list)
        assert isinstance(PROMO_CHANNEL_IDS, list)

    def test_bools(self):
        from bot.config import (
            THREAD_AUTO_REPLY, PROMO_ENABLED, OFFLINE_BACKFILL_ENABLED,
            DIGEST_ENABLED, WEBHOOK_ENABLED, ADMIN_ENABLED,
        )
        assert isinstance(THREAD_AUTO_REPLY, bool)
        assert isinstance(PROMO_ENABLED, bool)
        assert isinstance(OFFLINE_BACKFILL_ENABLED, bool)
        assert isinstance(DIGEST_ENABLED, bool)
        assert isinstance(WEBHOOK_ENABLED, bool)
        assert isinstance(ADMIN_ENABLED, bool)

    def test_centralized_digest_config(self):
        from bot.config import DIGEST_ENABLED, DIGEST_HOUR, DIGEST_CHANNEL_ID
        assert isinstance(DIGEST_ENABLED, bool)
        assert isinstance(DIGEST_HOUR, int)
        assert 0 <= DIGEST_HOUR <= 23
        assert isinstance(DIGEST_CHANNEL_ID, int)

    def test_centralized_webhook_config(self):
        from bot.config import WEBHOOK_ENABLED, WEBHOOK_PORT, WEBHOOK_SECRET
        assert isinstance(WEBHOOK_ENABLED, bool)
        assert isinstance(WEBHOOK_PORT, int)
        assert isinstance(WEBHOOK_SECRET, str)

    def test_centralized_admin_config(self):
        from bot.config import ADMIN_ENABLED, ADMIN_PORT, ADMIN_SECRET
        assert isinstance(ADMIN_ENABLED, bool)
        assert isinstance(ADMIN_PORT, int)
        assert isinstance(ADMIN_SECRET, str)

    def test_prompts_nonempty(self):
        from bot.config import SYSTEM_PROMPT_TEMPLATE, USER_PROMPT_TEMPLATE, DEFAULT_STYLE_GUIDELINES
        assert len(SYSTEM_PROMPT_TEMPLATE) > 100
        assert len(USER_PROMPT_TEMPLATE) > 20
        assert len(DEFAULT_STYLE_GUIDELINES) > 20


class TestParseIdList:
    def test_strips_spaces_and_inline_comments(self, monkeypatch):
        monkeypatch.setenv("TEST_IDS", "111, 222             # note")
        from bot.config import parse_id_list
        assert parse_id_list("TEST_IDS") == [111, 222]

    def test_empty(self, monkeypatch):
        monkeypatch.setenv("TEST_IDS_EMPTY", "")
        from bot.config import parse_id_list
        assert parse_id_list("TEST_IDS_EMPTY") == []
