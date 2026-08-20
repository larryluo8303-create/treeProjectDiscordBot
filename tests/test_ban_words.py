"""Tests for bot.ban_words — ban-word list with exact + semantic matching."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.ban_words import (
    _cosine_similarity,
    _ban_entries,
    add_ban_word,
    check_exact,
    check_semantic,
    get_ban_words,
    load_ban_words,
    refresh_embeddings,
    remove_ban_word,
    set_openai_client,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _reset_state():
    """Clear module state for test isolation."""
    import bot.ban_words as bw
    bw._ban_entries.clear()
    bw._exact_words.clear()
    bw._openai_client = None


class TestCosineSimilarity:
    def test_identical(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_similar(self):
        a = [1.0, 1.0]
        b = [1.0, 0.9]
        sim = _cosine_similarity(a, b)
        assert sim > 0.99


class TestCheckExact:
    def setup_method(self):
        _reset_state()

    def test_no_ban_words(self):
        assert check_exact("hello world") is None

    def test_match(self):
        import bot.ban_words as bw
        bw._ban_entries.append({"word": "scam", "embedding": None})
        bw._rebuild_exact()
        assert check_exact("this is a scam message") == "scam"

    def test_case_insensitive(self):
        import bot.ban_words as bw
        bw._ban_entries.append({"word": "SPAM", "embedding": None})
        bw._rebuild_exact()
        assert check_exact("some spam here") == "SPAM"

    def test_no_match(self):
        import bot.ban_words as bw
        bw._ban_entries.append({"word": "scam", "embedding": None})
        bw._rebuild_exact()
        assert check_exact("legitimate message") is None

    def test_chinese_match(self):
        import bot.ban_words as bw
        bw._ban_entries.append({"word": "诈骗", "embedding": None})
        bw._rebuild_exact()
        assert check_exact("这是一个诈骗消息") == "诈骗"


class TestCheckSemantic:
    def setup_method(self):
        _reset_state()

    @pytest.mark.asyncio
    async def test_no_client(self):
        """Without OpenAI client, semantic check returns None."""
        import bot.ban_words as bw
        bw._ban_entries.append({"word": "scam", "embedding": [1.0, 0.0]})
        result = await check_semantic("total scam")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_entries(self):
        result = await check_semantic("hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_short_message(self):
        """Messages shorter than 5 chars are skipped."""
        import bot.ban_words as bw
        bw._openai_client = MagicMock()
        bw._ban_entries.append({"word": "scam", "embedding": [1.0, 0.0]})
        result = await check_semantic("hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_match_above_threshold(self):
        import bot.ban_words as bw

        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_data = MagicMock()
        mock_data.embedding = [1.0, 0.0, 0.0]
        mock_response.data = [mock_data]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        bw._openai_client = mock_client

        # Add entry with very similar embedding
        bw._ban_entries.append({"word": "fraud", "embedding": [1.0, 0.0, 0.0]})

        result = await check_semantic("this is fraud")
        assert result is not None
        word, score = result
        assert word == "fraud"
        assert score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_match_below_threshold(self):
        import bot.ban_words as bw

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_data = MagicMock()
        mock_data.embedding = [1.0, 0.0, 0.0]
        mock_response.data = [mock_data]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        bw._openai_client = mock_client

        # Orthogonal embedding = 0 similarity
        bw._ban_entries.append({"word": "fraud", "embedding": [0.0, 1.0, 0.0]})

        result = await check_semantic("something unrelated here")
        assert result is None


class TestCRUD:
    def setup_method(self):
        _reset_state()

    @pytest.mark.asyncio
    async def test_add_ban_word(self):
        import bot.ban_words as bw
        # Patch _save to avoid disk writes
        with patch.object(bw, '_save'):
            ok = await add_ban_word("test_word")
            assert ok is True
            assert "test_word" in get_ban_words()

    @pytest.mark.asyncio
    async def test_add_duplicate(self):
        import bot.ban_words as bw
        with patch.object(bw, '_save'):
            await add_ban_word("dup")
            ok = await add_ban_word("DUP")  # case-insensitive
            assert ok is False

    @pytest.mark.asyncio
    async def test_add_empty(self):
        ok = await add_ban_word("")
        assert ok is False

    @pytest.mark.asyncio
    async def test_add_whitespace_only(self):
        ok = await add_ban_word("   ")
        assert ok is False

    def test_remove_ban_word(self):
        import bot.ban_words as bw
        bw._ban_entries.append({"word": "remove_me", "embedding": None})
        bw._rebuild_exact()
        with patch.object(bw, '_save'):
            ok = remove_ban_word("remove_me")
            assert ok is True
            assert "remove_me" not in get_ban_words()

    def test_remove_nonexistent(self):
        ok = remove_ban_word("nope")
        assert ok is False

    def test_remove_case_insensitive(self):
        import bot.ban_words as bw
        bw._ban_entries.append({"word": "CaseTest", "embedding": None})
        bw._rebuild_exact()
        with patch.object(bw, '_save'):
            ok = remove_ban_word("casetest")
            assert ok is True

    def test_get_ban_words_empty(self):
        assert get_ban_words() == []

    def test_get_ban_words(self):
        import bot.ban_words as bw
        bw._ban_entries.extend([
            {"word": "a", "embedding": None},
            {"word": "b", "embedding": None},
        ])
        assert get_ban_words() == ["a", "b"]


class TestPersistence:
    def setup_method(self):
        _reset_state()

    def test_load_missing_file(self):
        import bot.ban_words as bw
        with patch.object(bw, 'AUTO_MOD_BAN_WORDS_FILE', '/nonexistent/file.json'):
            load_ban_words()
            assert bw._ban_entries == []

    def test_load_valid_file(self, tmp_path):
        import bot.ban_words as bw
        f = tmp_path / "ban_words.json"
        f.write_text(json.dumps([{"word": "bad", "embedding": None}]), encoding="utf-8")
        with patch.object(bw, 'AUTO_MOD_BAN_WORDS_FILE', str(f)):
            load_ban_words()
            assert get_ban_words() == ["bad"]

    def test_load_corrupt_file(self, tmp_path):
        import bot.ban_words as bw
        f = tmp_path / "ban_words.json"
        f.write_text("not json!", encoding="utf-8")
        with patch.object(bw, 'AUTO_MOD_BAN_WORDS_FILE', str(f)):
            load_ban_words()
            assert bw._ban_entries == []


class TestRefreshEmbeddings:
    def setup_method(self):
        _reset_state()

    @pytest.mark.asyncio
    async def test_refresh_updates_missing(self):
        import bot.ban_words as bw

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_data = MagicMock()
        mock_data.embedding = [0.5, 0.5]
        mock_response.data = [mock_data]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        bw._openai_client = mock_client

        bw._ban_entries.append({"word": "test", "embedding": None})

        with patch.object(bw, '_save'):
            count = await refresh_embeddings()
            assert count == 1
            assert bw._ban_entries[0]["embedding"] == [0.5, 0.5]

    @pytest.mark.asyncio
    async def test_refresh_skips_existing(self):
        import bot.ban_words as bw

        bw._openai_client = AsyncMock()
        bw._ban_entries.append({"word": "test", "embedding": [1.0, 0.0]})

        with patch.object(bw, '_save'):
            count = await refresh_embeddings()
            assert count == 0


class TestSetOpenAIClient:
    def setup_method(self):
        _reset_state()

    def test_set_client(self):
        import bot.ban_words as bw
        mock = MagicMock()
        set_openai_client(mock)
        assert bw._openai_client is mock


class TestConfig:
    def test_defaults(self):
        from bot.config import AUTO_MOD_BAN_WORDS_FILE, AUTO_MOD_BAN_WORDS_SIMILARITY
        assert AUTO_MOD_BAN_WORDS_FILE.endswith("data/ban_words.json") or AUTO_MOD_BAN_WORDS_FILE.endswith("data\\ban_words.json")
        assert AUTO_MOD_BAN_WORDS_SIMILARITY == pytest.approx(0.82)
