"""Tests for ingestion.analyze_style module — ngram extraction, word count, style analysis."""

import json
import os
import tempfile

from ingestion.analyze_style import _extract_ngrams, _word_count, analyze_style


class TestExtractNgrams:
    def test_bigrams(self):
        result = _extract_ngrams("the quick brown fox", 2)
        assert result == ["the quick", "quick brown", "brown fox"]

    def test_trigrams(self):
        result = _extract_ngrams("one two three four", 3)
        assert result == ["one two three", "two three four"]

    def test_single_word_no_bigrams(self):
        assert _extract_ngrams("hello", 2) == []

    def test_empty_string(self):
        assert _extract_ngrams("", 2) == []

    def test_exact_n_words(self):
        assert _extract_ngrams("a b", 2) == ["a b"]


class TestWordCount:
    def test_english(self):
        assert _word_count("hello world") == 2

    def test_chinese(self):
        assert _word_count("你好世界") == 4  # 4 CJK characters

    def test_mixed(self):
        result = _word_count("AAPL 苹果公司 is great")
        # 3 CJK chars (苹果公) + non-CJK: AAPL, is, great = 3 + rest
        assert result > 3

    def test_empty(self):
        assert _word_count("") == 0

    def test_numbers(self):
        assert _word_count("price 42 is OK") == 4


class TestAnalyzeStyle:
    def _make_export_dir(self, messages):
        """Create a temp dir with a mock export JSON."""
        tmpdir = tempfile.mkdtemp()
        owner_id = "111111111111111111"
        export = {
            "channel": {"id": "999"},
            "messages": [
                {
                    "id": str(i),
                    "content": msg,
                    "timestamp": f"2024-01-01T00:{i:02d}:00+00:00",
                    "author": {"id": owner_id, "name": "Owner", "nickname": "Boss"},
                }
                for i, msg in enumerate(messages)
            ],
        }
        filepath = os.path.join(tmpdir, "export.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export, f, ensure_ascii=False)
        return tmpdir, owner_id

    def test_analyze_with_messages(self):
        messages = [
            "AAPL looking bullish today",
            "ES broke through resistance, watch for continuation",
            "Taking profit on half position",
            "Market is choppy, wait for clear direction",
            "NQ showing strong momentum above EMA13",
        ]
        tmpdir, owner_id = self._make_export_dir(messages)
        try:
            result = analyze_style(tmpdir, owner_id)
            assert "Style Profile" in result
            assert "Average response length" in result
            assert "Top phrases" in result
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_analyze_no_messages(self):
        tmpdir = tempfile.mkdtemp()
        # Empty export
        export = {"channel": {"id": "999"}, "messages": []}
        filepath = os.path.join(tmpdir, "export.json")
        with open(filepath, "w") as f:
            json.dump(export, f)
        try:
            result = analyze_style(tmpdir, "111111111111111111")
            assert "No owner messages" in result
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_analyze_empty_dir(self):
        tmpdir = tempfile.mkdtemp()
        try:
            result = analyze_style(tmpdir, "111111111111111111")
            assert "No owner messages" in result
        finally:
            os.rmdir(tmpdir)
