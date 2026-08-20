"""Tests for the ingestion preprocessing pipeline."""

import json
import os
import tempfile

from ingestion.preprocess import (
    build_qa_pairs,
    chunk_text,
    clean_message,
    filter_owner_messages,
    group_consecutive,
    load_exports,
    preprocess_all,
)

OWNER_ID = "111111111111111111"
OTHER_ID = "222222222222222222"


def _make_export(messages: list[dict], channel_id: str = "999") -> dict:
    return {
        "channel": {"id": channel_id},
        "messages": messages,
    }


def _make_msg(
    msg_id: str,
    content: str,
    author_id: str = OWNER_ID,
    timestamp: str = "2024-01-01T00:00:00+00:00",
    reference_id: str | None = None,
) -> dict:
    msg = {
        "id": msg_id,
        "content": content,
        "timestamp": timestamp,
        "author": {"id": author_id, "name": "TestUser", "nickname": "TestNick"},
    }
    if reference_id:
        msg["reference"] = {"messageId": reference_id}
    return msg


class TestFilterOwnerMessages:
    def test_filters_correctly(self):
        msgs = [
            _make_msg("1", "hello", OWNER_ID),
            _make_msg("2", "world", OTHER_ID),
            _make_msg("3", "foo", OWNER_ID),
        ]
        result = filter_owner_messages(msgs, OWNER_ID)
        assert len(result) == 2
        assert all(m["author"]["id"] == OWNER_ID for m in result)


class TestBuildQAPairs:
    def test_builds_pairs_from_replies(self):
        msgs = [
            _make_msg("1", "What stock to buy?", OTHER_ID, "2024-01-01T00:00:00+00:00"),
            _make_msg("2", "I like AAPL right now", OWNER_ID, "2024-01-01T00:01:00+00:00", reference_id="1"),
        ]
        pairs = build_qa_pairs(msgs, OWNER_ID)
        assert len(pairs) == 1
        assert "Q: What stock to buy?" in pairs[0]["text"]
        assert "A: I like AAPL right now" in pairs[0]["text"]
        assert pairs[0]["metadata"]["type"] == "qa_pair"

    def test_skips_self_replies(self):
        msgs = [
            _make_msg("1", "Let me add to this", OWNER_ID, "2024-01-01T00:00:00+00:00"),
            _make_msg("2", "More info here", OWNER_ID, "2024-01-01T00:01:00+00:00", reference_id="1"),
        ]
        pairs = build_qa_pairs(msgs, OWNER_ID)
        assert len(pairs) == 0


class TestGroupConsecutive:
    def test_groups_within_window(self):
        msgs = [
            _make_msg("1", "First part", OWNER_ID, "2024-01-01T00:00:00+00:00"),
            _make_msg("2", "Second part", OWNER_ID, "2024-01-01T00:01:00+00:00"),
            _make_msg("3", "Third part", OWNER_ID, "2024-01-01T00:01:30+00:00"),
        ]
        groups = group_consecutive(msgs, OWNER_ID, window_seconds=120)
        assert len(groups) == 1
        assert "First part" in groups[0]["text"]
        assert "Second part" in groups[0]["text"]
        assert "Third part" in groups[0]["text"]
        assert groups[0]["metadata"]["type"] == "grouped"

    def test_separates_by_time_gap(self):
        msgs = [
            _make_msg("1", "First message", OWNER_ID, "2024-01-01T00:00:00+00:00"),
            _make_msg("2", "Second message", OWNER_ID, "2024-01-01T01:00:00+00:00"),
        ]
        groups = group_consecutive(msgs, OWNER_ID, window_seconds=120)
        assert len(groups) == 2


class TestCleanMessage:
    def test_resolves_mentions(self):
        users = {OTHER_ID: {"name": "Bob", "nickname": "Bobby"}}
        content = f"Hey <@{OTHER_ID}> check this out"
        result = clean_message(content, users)
        assert "@Bobby" in result
        assert f"<@{OTHER_ID}>" not in result

    def test_strips_custom_emoji(self):
        content = "Nice trade <:rocket:123456>"
        result = clean_message(content, {})
        assert ":rocket:" in result
        assert "<:rocket:123456>" not in result


class TestChunkText:
    def test_short_text_not_chunked(self):
        text = "This is a short message."
        chunks = chunk_text(text, max_tokens=500)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_chunked(self):
        text = " ".join(["word"] * 1000)  # ~1000 tokens
        chunks = chunk_text(text, max_tokens=100, overlap=0)
        assert len(chunks) > 1


class TestLoadExports:
    def test_loads_from_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            export = _make_export([
                _make_msg("1", "hello", OWNER_ID),
                _make_msg("2", "world", OTHER_ID),
            ])
            filepath = os.path.join(tmpdir, "export.json")
            with open(filepath, "w") as f:
                json.dump(export, f)

            messages, users = load_exports(tmpdir)
            assert len(messages) == 2
            assert OWNER_ID in users


class TestPreprocessAll:
    def test_full_pipeline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            export = _make_export([
                _make_msg("1", "What is AAPL doing?", OTHER_ID, "2024-01-01T00:00:00+00:00"),
                _make_msg("2", "AAPL is looking bullish, support at 180", OWNER_ID, "2024-01-01T00:01:00+00:00", reference_id="1"),
                _make_msg("3", "Also watching the weekly chart", OWNER_ID, "2024-01-01T00:01:30+00:00"),
            ])
            filepath = os.path.join(tmpdir, "export.json")
            with open(filepath, "w") as f:
                json.dump(export, f)

            docs = preprocess_all(tmpdir, OWNER_ID)
            assert len(docs) > 0
            # Should have at least one Q&A pair
            qa_docs = [d for d in docs if d["metadata"]["type"] == "qa_pair"]
            assert len(qa_docs) >= 1
