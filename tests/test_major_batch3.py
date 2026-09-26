"""Regression tests for Major batch 3 (ingestion/data pipeline).

- group_consecutive: a non-owner message between two owner messages breaks
  the group (implementation now matches its docstring)
- preprocess_all dedup: a grouped block is dropped only when EVERY message in
  it already appears in a Q&A pair (no more whole-group data loss)
- PDF chunk IDs are content-addressed (content hash in the ID seed)
- load_exports skips corrupt JSON files instead of crashing the run
- _remove_stale_chunks deletes replaced-file chunks (incl. old-scheme ones)
"""

import hashlib
import json
import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("chromadb", MagicMock())


def _msg(mid, author_id, content, ts, channel="c1", ref=None):
    m = {
        "id": mid,
        "author": {"id": author_id},
        "content": content,
        "timestamp": ts,
        "_channel_id": channel,
    }
    if ref:
        m["reference"] = {"messageId": ref}
    return m


OWNER = "owner1"
USER = "user9"


def test_non_owner_message_breaks_group():
    from ingestion.preprocess import group_consecutive
    msgs = [
        _msg("m1", OWNER, "第一句", "2024-01-01T10:00:00+00:00"),
        _msg("m2", USER, "插话", "2024-01-01T10:00:30+00:00"),
        _msg("m3", OWNER, "第二句", "2024-01-01T10:01:00+00:00"),
    ]
    groups = group_consecutive(msgs, OWNER, window_seconds=120)
    # m1 and m3 must NOT be merged: the user message breaks the run
    assert len(groups) == 2
    assert groups[0]["text"] == "第一句"
    assert groups[1]["text"] == "第二句"


def test_consecutive_owner_messages_still_merge():
    from ingestion.preprocess import group_consecutive
    msgs = [
        _msg("m1", OWNER, "第一句", "2024-01-01T10:00:00+00:00"),
        _msg("m2", OWNER, "第二句", "2024-01-01T10:00:30+00:00"),
    ]
    groups = group_consecutive(msgs, OWNER, window_seconds=120)
    assert len(groups) == 1
    assert "第一句" in groups[0]["text"] and "第二句" in groups[0]["text"]
    assert groups[0]["metadata"]["type"] == "grouped"
    # full id set carried for dedup
    assert set(groups[0]["metadata"]["source_message_ids"]) == {"m1", "m2"}


def test_group_time_gap_splits():
    from ingestion.preprocess import group_consecutive
    msgs = [
        _msg("m1", OWNER, "早", "2024-01-01T10:00:00+00:00"),
        _msg("m2", OWNER, "晚", "2024-01-01T12:00:00+00:00"),
    ]
    groups = group_consecutive(msgs, OWNER, window_seconds=120)
    assert len(groups) == 2


def test_dedup_keeps_partially_overlapping_group(tmp_path):
    """Only fully Q&A-covered groups are dropped; partial overlap is kept."""
    from ingestion import preprocess as pp
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    (export_dir / "ch.json").write_text(json.dumps({
        "channel": {"id": "c1"},
        "messages": [
            _msg("q1", USER, "AAPL怎么看？", "2024-01-01T10:00:00+00:00"),
            _msg("a1", OWNER, "我觉得能涨", "2024-01-01T10:00:20+00:00", ref="q1"),
            _msg("a2", OWNER, "补充一个观点", "2024-01-01T10:00:40+00:00"),
        ],
    }), encoding="utf-8")

    docs = pp.preprocess_all(str(export_dir), OWNER, max_tokens=500, overlap=0)
    texts = [d["text"] for d in docs]
    # Q&A pair present
    assert any("AAPL怎么看" in t for t in texts)
    # a2 was grouped with a1; the old code dropped the whole group because a1
    # was in a Q&A pair — a2's content must survive now.
    assert any("补充一个观点" in t for t in texts)


def test_dedup_drops_fully_covered_group(tmp_path):
    from ingestion import preprocess as pp
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    (export_dir / "ch.json").write_text(json.dumps({
        "channel": {"id": "c1"},
        "messages": [
            _msg("q1", USER, "TSLA怎么看？", "2024-01-01T10:00:00+00:00"),
            _msg("a1", OWNER, "持有", "2024-01-01T10:00:20+00:00", ref="q1"),
        ],
    }), encoding="utf-8")

    docs = pp.preprocess_all(str(export_dir), OWNER, max_tokens=500, overlap=0)
    # Only the Q&A pair; the standalone "持有" group is fully covered -> dropped
    assert len([d for d in docs if d["metadata"]["type"] == "qa_pair"]) == 1
    assert not any(d["metadata"]["type"] == "standalone" for d in docs)


def test_pdf_ids_are_content_addressed():
    from ingestion.ingest_pdf import _build_documents
    pages = [(1, "Some page text with enough content to chunk.")]
    d1 = _build_documents(pages, "/x/a.pdf", "src", "hashAAA", 500, 0)
    d2 = _build_documents(pages, "/x/a.pdf", "src", "hashAAA", 500, 0)
    d3 = _build_documents(pages, "/x/a.pdf", "src", "hashBBB", 500, 0)
    assert d1[0]["id"] == d2[0]["id"]          # same bytes -> same IDs
    assert d1[0]["id"] != d3[0]["id"]          # replaced file -> new IDs
    assert d1[0]["metadata"]["content_hash"] == "hashAAA"


def test_file_content_hash_detects_replacement(tmp_path):
    from ingestion.ingest_pdf import _file_content_hash
    f = tmp_path / "book.pdf"
    f.write_bytes(b"version one bytes")
    h1 = _file_content_hash(str(f))
    f.write_bytes(b"version two bytes!!")
    h2 = _file_content_hash(str(f))
    assert h1 != h2 and len(h1) == 16


def test_remove_stale_chunks(tmp_path):
    from ingestion.ingest_pdf import _remove_stale_chunks
    col = MagicMock()
    col.get.return_value = {
        "ids": ["old1", "old2", "current1"],
        "metadatas": [
            {"filename": "b.pdf"},  # old scheme: no content_hash -> stale
            {"filename": "b.pdf", "content_hash": "deadbeef"},
            {"filename": "b.pdf", "content_hash": "newhash"},
        ],
    }
    removed = _remove_stale_chunks(col, "b.pdf", "newhash")
    assert removed == 2
    deleted_ids = col.delete.call_args.kwargs["ids"]
    assert set(deleted_ids) == {"old1", "old2"}


def test_load_exports_skips_corrupt_json(tmp_path):
    from ingestion.preprocess import load_exports
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    (export_dir / "good.json").write_text(json.dumps({
        "channel": {"id": "c1"},
        "messages": [_msg("m1", OWNER, "hello", "2024-01-01T10:00:00+00:00")],
    }), encoding="utf-8")
    (export_dir / "bad.json").write_text("{ this is not valid json !!!", encoding="utf-8")
    messages, users = load_exports(str(export_dir))
    assert [m["id"] for m in messages] == ["m1"]
    assert users[OWNER]["name"] == ""
