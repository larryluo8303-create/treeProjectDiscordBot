"""Tests for ingestion.ingest module — token truncation, dedup, metadata sanitization."""

from ingestion.ingest import _truncate_to_tokens, _ENC, EMBEDDING_MAX_TOKENS


class TestTruncateToTokens:
    def test_short_text_unchanged(self):
        text = "This is a short text."
        result = _truncate_to_tokens(text, max_tokens=100)
        assert result == text

    def test_long_text_truncated(self):
        text = "word " * 10000  # ~10000 tokens
        result = _truncate_to_tokens(text, max_tokens=50)
        tokens = _ENC.encode(result)
        assert len(tokens) <= 50

    def test_exact_limit_unchanged(self):
        tokens = _ENC.encode("hello world this is a test")
        text = _ENC.decode(tokens)
        result = _truncate_to_tokens(text, max_tokens=len(tokens))
        assert result == text

    def test_empty_text(self):
        assert _truncate_to_tokens("", max_tokens=100) == ""

    def test_chinese_text_truncation(self):
        text = "你好世界" * 500  # many Chinese characters
        result = _truncate_to_tokens(text, max_tokens=50)
        tokens = _ENC.encode(result)
        assert len(tokens) <= 50

    def test_default_limit(self):
        assert EMBEDDING_MAX_TOKENS == 8191


class TestIngestHelpers:
    def test_embed_batch_metadata_sanitization(self):
        """Verify the metadata sanitization logic works correctly."""
        # This tests the inline sanitization code pattern
        raw_meta = {
            "type": "qa_pair",
            "count": 42,
            "score": 0.95,
            "active": True,
            "tags": ["a", "b"],  # list → should become str
            "nested": {"key": "val"},  # dict → should become str
        }
        clean_meta = {}
        for k, v in raw_meta.items():
            if isinstance(v, (str, int, float, bool)):
                clean_meta[k] = v
            else:
                clean_meta[k] = str(v)

        assert clean_meta["type"] == "qa_pair"
        assert clean_meta["count"] == 42
        assert clean_meta["score"] == 0.95
        assert clean_meta["active"] is True
        assert clean_meta["tags"] == "['a', 'b']"
        assert clean_meta["nested"] == "{'key': 'val'}"

    def test_dedup_logic(self):
        """Test the ID dedup pattern used in ingest_to_chromadb."""
        import uuid

        ids = ["doc_1", "doc_2", "doc_1", "doc_3", "doc_1"]
        seen: set[str] = set()
        unique_ids: list[str] = []
        for doc_id in ids:
            if doc_id in seen:
                doc_id = f"{doc_id}_{uuid.uuid4().hex[:8]}"
            seen.add(doc_id)
            unique_ids.append(doc_id)

        assert len(unique_ids) == 5
        assert len(set(unique_ids)) == 5  # all unique
        assert unique_ids[0] == "doc_1"
        assert unique_ids[1] == "doc_2"
        assert unique_ids[2].startswith("doc_1_")
        assert unique_ids[3] == "doc_3"
        assert unique_ids[4].startswith("doc_1_")
