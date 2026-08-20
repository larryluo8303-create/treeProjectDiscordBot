"""Knowledge base version management — snapshot & rollback.

Before each ingestion, takes a lightweight snapshot of the ChromaDB
collection metadata so the owner can /kb_rollback to a previous version.

Snapshots are stored in ``data/kb_snapshots/``.
"""

import json
import logging
import os
import shutil
import time

from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

KB_SNAPSHOTS_DIR = data_path(os.getenv("KB_SNAPSHOTS_DIR", "data/kb_snapshots"))
_MAX_SNAPSHOTS = 10


def _ensure_dir() -> None:
    os.makedirs(KB_SNAPSHOTS_DIR, exist_ok=True)


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


def create_snapshot(doc_count: int, description: str = "") -> dict:
    """Create a new snapshot record (metadata only — ChromaDB data is on disk).

    Parameters
    ----------
    doc_count : int
        Current number of documents in the collection.
    description : str
        Optional description of the snapshot.

    Returns
    -------
    dict
        The snapshot metadata.
    """
    _ensure_dir()
    snapshots = list_snapshots()
    snapshot = {
        "id": f"snap_{int(time.time())}",
        "timestamp": time.time(),
        "doc_count": doc_count,
        "description": description or f"Snapshot with {doc_count} documents",
    }
    snapshots.insert(0, snapshot)
    # Keep only the most recent snapshots
    snapshots = snapshots[:_MAX_SNAPSHOTS]
    _save_index(snapshots)
    logger.info("KB snapshot created: %s (docs=%d)", snapshot["id"], doc_count)
    return snapshot


def get_snapshot(snapshot_id: str) -> dict | None:
    """Find a snapshot by ID."""
    for s in list_snapshots():
        if s["id"] == snapshot_id:
            return s
    return None


def delete_old_snapshots(keep: int = _MAX_SNAPSHOTS) -> int:
    """Remove oldest snapshots beyond *keep*. Returns count deleted."""
    snapshots = list_snapshots()
    if len(snapshots) <= keep:
        return 0
    removed = snapshots[keep:]
    snapshots = snapshots[:keep]
    _save_index(snapshots)
    return len(removed)
