"""Knowledge base version management — real ChromaDB snapshots + rollback.

Before each ingestion, call :func:`create_snapshot` to copy the whole
ChromaDB persistence directory into ``data/kb_snapshots/<snapshot_id>/``.
If an ingestion corrupts the KB, :func:`rollback_snapshot` restores a
previous snapshot — the pre-rollback state is itself saved as a snapshot
first, so a bad rollback can be undone.

Consistency note: snapshots are plain on-disk copies.  For a fully
consistent snapshot, take it while the bot is idle (a live ChromaDB/SQLite
may be mid-write).  The copy itself never touches the live directory, and
rollback always backs up the current state before replacing it.

Snapshots are stored in ``data/kb_snapshots/`` (see ``KB_SNAPSHOTS_DIR``).
"""

import json
import logging
import os
import shutil
import time

from bot.config import CHROMADB_PATH
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

KB_SNAPSHOTS_DIR = data_path(os.getenv("KB_SNAPSHOTS_DIR", "data/kb_snapshots"))
# Resolved exactly the way bot/main.py opens it:
# chromadb.PersistentClient(path=CHROMADB_PATH)
CHROMA_DIR = CHROMADB_PATH
_MAX_SNAPSHOTS = 10
# Snapshot size above this logs a warning so the caller can decide whether
# a full copy is worth it (large KBs make snapshots slow and disk-hungry).
_WARN_SIZE_BYTES = 500 * 1024 * 1024


def _ensure_dir() -> None:
    os.makedirs(KB_SNAPSHOTS_DIR, exist_ok=True)


def _dir_size_bytes(path: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                continue
    return total


def _unique_snapshot_id(prefix: str) -> str:
    base = f"{prefix}_{int(time.time())}"
    candidate = base
    n = 1
    while os.path.exists(os.path.join(KB_SNAPSHOTS_DIR, candidate)):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _check_size_warned(src: str) -> int:
    """Return dir size; log a warning when it exceeds the copy threshold."""
    size_bytes = _dir_size_bytes(src)
    if size_bytes > _WARN_SIZE_BYTES:
        logger.warning(
            "ChromaDB dir is %.1f MB (> %d MB) — snapshot will be slow and "
            "disk-hungry; caller should decide whether to proceed.",
            size_bytes / (1024 * 1024),
            _WARN_SIZE_BYTES // (1024 * 1024),
        )
    return size_bytes


def list_snapshots() -> list[dict]:
    """Return all snapshots sorted by timestamp (newest first)."""
    _ensure_dir()
    index_path = os.path.join(KB_SNAPSHOTS_DIR, "index.json")
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            snapshots = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        snapshots = []
    snapshots.sort(key=lambda s: s.get("timestamp", 0), reverse=True)
    return snapshots


def _save_index(snapshots: list[dict]) -> None:
    _ensure_dir()
    index_path = os.path.join(KB_SNAPSHOTS_DIR, "index.json")
    atomic_json_write(index_path, snapshots, ensure_ascii=False, indent=2)


def _record_snapshot(snapshot_id: str, doc_count: int, description: str,
                     size_bytes: int) -> dict:
    """Write the index entry for an already-copied snapshot dir."""
    snapshot = {
        "id": snapshot_id,
        "timestamp": time.time(),
        "doc_count": doc_count,
        "description": description or f"Snapshot with {doc_count} documents",
        "size_bytes": size_bytes,
    }
    snapshots = list_snapshots()
    snapshots.insert(0, snapshot)
    _save_index(snapshots)
    delete_old_snapshots()
    return snapshot


def create_snapshot(doc_count: int, description: str = "") -> dict:
    """Snapshot the live ChromaDB directory to ``data/kb_snapshots/<id>/``.

    Parameters
    ----------
    doc_count : int
        Current number of documents in the collection (recorded in metadata).
    description : str
        Optional description of the snapshot.

    Returns
    -------
    dict
        Snapshot metadata: {id, timestamp, doc_count, description,
        size_bytes}.

    Raises
    ------
    FileNotFoundError
        If the ChromaDB directory does not exist.
    """
    _ensure_dir()
    src = CHROMA_DIR
    if not os.path.isdir(src):
        raise FileNotFoundError(
            f"ChromaDB directory not found: {src!r} — "
            "nothing to snapshot (run ingestion first)."
        )
    size_bytes = _check_size_warned(src)
    snapshot_id = _unique_snapshot_id("snap")
    shutil.copytree(src, os.path.join(KB_SNAPSHOTS_DIR, snapshot_id))
    snapshot = _record_snapshot(snapshot_id, doc_count, description, size_bytes)
    logger.info(
        "KB snapshot created: %s (docs=%d, size=%.1f MB)",
        snapshot_id,
        doc_count,
        size_bytes / (1024 * 1024),
    )
    return snapshot


def get_snapshot(snapshot_id: str) -> dict | None:
    """Find a snapshot by ID."""
    for s in list_snapshots():
        if s["id"] == snapshot_id:
            return s
    return None


def rollback_snapshot(snapshot_id: str) -> dict | None:
    """Restore the live ChromaDB directory from a snapshot.

    The current state is first backed up as its own ``pre-rollback-<ts>``
    snapshot (when a live directory exists), so a bad rollback can itself
    be rolled back.

    Parameters
    ----------
    snapshot_id : str
        ID of the snapshot to restore.

    Returns
    -------
    dict | None
        Metadata of the auto-created pre-rollback backup snapshot, or None
        when there was no live directory to back up.

    Raises
    ------
    KeyError
        If no snapshot with *snapshot_id* exists.
    FileNotFoundError
        If the snapshot's data directory is missing on disk.
    RuntimeError
        If the restore fails after the live directory was replaced —
        the pre-rollback backup ID is included so it can be restored
        manually.
    """
    snap = get_snapshot(snapshot_id)
    if snap is None:
        raise KeyError(f"Unknown KB snapshot: {snapshot_id!r}")
    src = os.path.join(KB_SNAPSHOTS_DIR, snapshot_id)
    if not os.path.isdir(src):
        raise FileNotFoundError(
            f"Snapshot data directory missing: {src!r} — "
            "the snapshot record exists but its files are gone."
        )

    # 1. Back up the current state first — a bad rollback stays undoable.
    backup = None
    live = CHROMA_DIR
    if os.path.isdir(live):
        pre_id = _unique_snapshot_id("pre-rollback")
        size_bytes = _check_size_warned(live)
        shutil.copytree(live, os.path.join(KB_SNAPSHOTS_DIR, pre_id))
        backup = _record_snapshot(
            pre_id,
            snap.get("doc_count", -1),
            f"Auto-backup before rollback to {snapshot_id}",
            size_bytes,
        )
    else:
        logger.warning(
            "Live ChromaDB dir %r missing — restoring %r without backup.",
            live, snapshot_id,
        )

    # 2. Replace the live directory with the snapshot copy.
    try:
        if os.path.isdir(live) or os.path.islink(live):
            shutil.rmtree(live)
        shutil.copytree(src, live)
    except Exception as exc:
        hint = (f"the pre-rollback backup {backup['id']!r} is intact — "
                f"restore it with rollback_snapshot({backup['id']!r})"
                ) if backup else "no pre-rollback backup exists"
        raise RuntimeError(
            f"KB rollback to {snapshot_id!r} failed mid-restore ({exc}); {hint}."
        ) from exc

    logger.info("KB rolled back to snapshot %s (pre-rollback backup: %s)",
                snapshot_id, backup["id"] if backup else "none")
    return backup


def delete_old_snapshots(keep: int | None = None) -> int:
    """Remove oldest snapshots beyond *keep*, including their data dirs.

    Returns count deleted.
    """
    if keep is None:
        keep = _MAX_SNAPSHOTS  # read at call time so tests can patch it
    snapshots = list_snapshots()
    if len(snapshots) <= keep:
        return 0
    removed = snapshots[keep:]
    snapshots = snapshots[:keep]
    _save_index(snapshots)
    for snap in removed:
        snap_dir = os.path.join(KB_SNAPSHOTS_DIR, snap.get("id", ""))
        if os.path.isdir(snap_dir):
            try:
                shutil.rmtree(snap_dir)
            except OSError as exc:
                logger.warning("Could not remove old snapshot dir %s: %s",
                               snap_dir, exc)
    return len(removed)
