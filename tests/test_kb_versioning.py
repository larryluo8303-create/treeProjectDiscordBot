"""Tests for real KB snapshot/rollback (bot/kb_versioning.py).

All tests use temp dirs via monkeypatched module globals — the real
``data/`` tree is never touched.
"""

import logging
import os

import pytest

import bot.kb_versioning as kbv


@pytest.fixture
def fake_dirs(tmp_path, monkeypatch):
    """Fake ChromaDB dir + fake snapshots dir, both under tmp_path."""
    chroma = tmp_path / "chroma_store"
    chroma.mkdir()
    (chroma / "chroma.sqlite3").write_text("v1-data")
    (chroma / "index").mkdir()
    (chroma / "index" / "segment.bin").write_text("segment-bytes")
    snaps = tmp_path / "kb_snapshots"
    monkeypatch.setattr(kbv, "CHROMA_DIR", str(chroma))
    monkeypatch.setattr(kbv, "KB_SNAPSHOTS_DIR", str(snaps))
    return chroma, snaps


def _read(chroma, name="chroma.sqlite3"):
    return (chroma / name).read_text()


class TestCreateSnapshot:
    def test_copies_live_dir_and_records_metadata(self, fake_dirs):
        chroma, snaps = fake_dirs
        snap = kbv.create_snapshot(42, "before ingest")
        assert snap["id"].startswith("snap_")
        assert snap["doc_count"] == 42
        assert snap["description"] == "before ingest"
        assert snap["size_bytes"] > 0
        # Full copy on disk, including nested dirs
        assert (snaps / snap["id"] / "chroma.sqlite3").read_text() == "v1-data"
        assert (snaps / snap["id"] / "index" / "segment.bin").read_text() == "segment-bytes"
        # Index lists it
        assert kbv.get_snapshot(snap["id"])["id"] == snap["id"]

    def test_unique_ids_within_same_second(self, fake_dirs):
        _, snaps = fake_dirs
        a = kbv.create_snapshot(1)
        b = kbv.create_snapshot(2)
        assert a["id"] != b["id"]
        assert (snaps / a["id"]).is_dir()
        assert (snaps / b["id"]).is_dir()

    def test_missing_chroma_dir_raises(self, fake_dirs, monkeypatch):
        monkeypatch.setattr(kbv, "CHROMA_DIR", "/nonexistent-chroma-dir-xyz")
        with pytest.raises(FileNotFoundError):
            kbv.create_snapshot(10)

    def test_large_dir_logs_warning(self, fake_dirs, monkeypatch, caplog):
        monkeypatch.setattr(kbv, "_WARN_SIZE_BYTES", 1)  # 1 byte threshold
        with caplog.at_level(logging.WARNING, logger="bot.kb_versioning"):
            kbv.create_snapshot(5)
        assert any("disk-hungry" in r.message for r in caplog.records)


class TestRollbackSnapshot:
    def test_rollback_restores_and_backs_up(self, fake_dirs):
        chroma, snaps = fake_dirs
        snap = kbv.create_snapshot(10, "good state")
        # Simulate a bad ingestion mutating the live dir
        (chroma / "chroma.sqlite3").write_text("corrupted-data")
        (chroma / "new_junk.bin").write_text("junk")

        backup = kbv.rollback_snapshot(snap["id"])

        # Live dir restored to snapshot content
        assert _read(chroma) == "v1-data"
        assert not (chroma / "new_junk.bin").exists()
        # Pre-rollback backup captured the corrupted state
        assert backup is not None
        assert backup["id"].startswith("pre-rollback_")
        assert (snaps / backup["id"] / "chroma.sqlite3").read_text() == "corrupted-data"
        assert (snaps / backup["id"] / "new_junk.bin").read_text() == "junk"
        # And the bad rollback itself is undoable
        kbv.rollback_snapshot(backup["id"])
        assert _read(chroma) == "corrupted-data"

    def test_rollback_unknown_id_raises(self, fake_dirs):
        with pytest.raises(KeyError):
            kbv.rollback_snapshot("snap_does_not_exist")

    def test_rollback_missing_data_dir_raises(self, fake_dirs):
        _, snaps = fake_dirs
        snap = kbv.create_snapshot(3)
        # Index record exists but files were deleted out-of-band
        import shutil
        shutil.rmtree(snaps / snap["id"])
        with pytest.raises(FileNotFoundError):
            kbv.rollback_snapshot(snap["id"])

    def test_rollback_without_live_dir_still_restores(self, fake_dirs, monkeypatch):
        chroma, snaps = fake_dirs
        snap = kbv.create_snapshot(7)
        import shutil
        shutil.rmtree(chroma)  # live dir gone entirely
        assert not os.path.exists(str(chroma))
        backup = kbv.rollback_snapshot(snap["id"])
        assert backup is None  # nothing to back up
        assert _read(chroma) == "v1-data"


class TestDeleteOldSnapshots:
    def test_removes_data_dirs_from_disk(self, fake_dirs, monkeypatch):
        _, snaps = fake_dirs
        monkeypatch.setattr(kbv, "_MAX_SNAPSHOTS", 100)  # don't auto-trim
        ids = [kbv.create_snapshot(i)["id"] for i in range(4)]
        assert kbv.delete_old_snapshots(keep=2) == 2
        remaining = {s["id"] for s in kbv.list_snapshots()}
        assert len(remaining) == 2
        for old_id in ids:
            if old_id not in remaining:
                assert not (snaps / old_id).exists(), f"{old_id} dir leaked on disk"
