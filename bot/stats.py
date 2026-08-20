"""In-memory statistics tracker with periodic JSON persistence.

Tracks:
- Total queries processed
- Auto-replies vs owner-forwards
- Average confidence score
- Average response latency (ms)
- Per-channel query counts
- Recent top questions (rolling window)
"""

import asyncio
import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

STATS_FILE = data_path(os.getenv("STATS_FILE", "data/stats.json"))
_SAVE_INTERVAL = 60  # seconds


@dataclass
class QueryRecord:
    question: str
    channel_id: int
    confidence: int
    action: str  # "auto_reply" or "forward"
    latency_ms: int
    timestamp: float = field(default_factory=time.time)


class BotStats:
    """Thread-safe (single-event-loop) statistics collector."""

    def __init__(self) -> None:
        self.total_queries: int = 0
        self.auto_replies: int = 0
        self.forwards: int = 0
        self.total_confidence: int = 0
        self.total_latency_ms: int = 0
        self.channel_counts: dict[int, int] = {}
        # All query records (persisted to disk)
        self.recent: deque[QueryRecord] = deque()
        self._save_task: asyncio.Task | None = None
        self._dirty: bool = False
        self._load()

    # ── Public API ────────────────────────────────────────────────────────

    def record_query(
        self,
        question: str,
        channel_id: int,
        confidence: int,
        action: str,
        latency_ms: int,
    ) -> None:
        """Record a processed query."""
        self.total_queries += 1
        self.total_confidence += confidence
        self.total_latency_ms += latency_ms

        if action == "auto_reply":
            self.auto_replies += 1
        else:
            self.forwards += 1

        self.channel_counts[channel_id] = self.channel_counts.get(channel_id, 0) + 1
        self.recent.append(QueryRecord(
            question=question[:200],
            channel_id=channel_id,
            confidence=confidence,
            action=action,
            latency_ms=latency_ms,
        ))
        self._dirty = True

    @property
    def avg_confidence(self) -> float:
        return self.total_confidence / self.total_queries if self.total_queries else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.total_queries if self.total_queries else 0.0

    def _filter_by_range(self, range_key: str) -> list[QueryRecord]:
        """Return records matching a time range key.

        Supported keys: '24h', '7d', '30d', '90d', '365d', 'all'.
        """
        if range_key == "all":
            return list(self.recent)
        multipliers = {"24h": 86400, "7d": 604800, "30d": 2592000, "90d": 7776000, "365d": 31536000}
        seconds = multipliers.get(range_key)
        if seconds is None:
            return list(self.recent)
        cutoff = time.time() - seconds
        return [r for r in self.recent if r.timestamp >= cutoff]

    def _compute_from_records(self, records: list["QueryRecord"], range_key: str) -> dict[str, Any]:
        """Build a stats dict from a list of QueryRecord objects."""
        total = len(records)
        auto = sum(1 for r in records if r.action == "auto_reply")
        fwd = total - auto
        total_conf = sum(r.confidence for r in records)
        total_lat = sum(r.latency_ms for r in records)
        chan: dict[int, int] = {}
        for r in records:
            chan[r.channel_id] = chan.get(r.channel_id, 0) + 1
        return {
            "range": range_key,
            "total_queries": total,
            "auto_replies": auto,
            "forwards": fwd,
            "avg_confidence": round(total_conf / total, 2) if total else 0.0,
            "avg_latency_ms": round(total_lat / total, 1) if total else 0.0,
            "top_channels": dict(
                sorted(chan.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
        }

    def snapshot(self, range_key: str = "all") -> dict[str, Any]:
        """Return a JSON-serializable snapshot of stats for a time range."""
        records = self._filter_by_range(range_key)
        return self._compute_from_records(records, range_key)

    def top_questions(self, limit: int = 10, range_key: str = "all") -> list[dict]:
        """Return recent questions sorted by recency, optionally filtered by time range."""
        records = self._filter_by_range(range_key)
        items = records[-limit:]
        items.reverse()
        return [
            {
                "question": r.question,
                "confidence": r.confidence,
                "action": r.action,
                "latency_ms": r.latency_ms,
            }
            for r in items
        ]

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load persisted stats from disk."""
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.total_queries = data.get("total_queries", 0)
            self.auto_replies = data.get("auto_replies", 0)
            self.forwards = data.get("forwards", 0)
            self.total_confidence = data.get("total_confidence", 0)
            self.total_latency_ms = data.get("total_latency_ms", 0)
            self.channel_counts = {int(k): v for k, v in data.get("channel_counts", {}).items()}
            now = time.time()
            for r in data.get("recent", []):
                try:
                    ts = float(r.get("timestamp", 0))
                    if ts < 1000000000:  # before 2001 — missing/invalid timestamp
                        ts = now
                    self.recent.append(QueryRecord(
                        question=r["question"],
                        channel_id=int(r["channel_id"]),
                        confidence=int(r["confidence"]),
                        action=r["action"],
                        latency_ms=int(r["latency_ms"]),
                        timestamp=ts,
                    ))
                except (KeyError, ValueError, TypeError):
                    continue
            logger.info("Loaded stats from %s (total_queries=%d, recent=%d)", STATS_FILE, self.total_queries, len(self.recent))
        except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
            logger.info("No existing stats file — starting fresh")

    def _save(self) -> None:
        """Persist stats to disk atomically."""
        data = {
            "total_queries": self.total_queries,
            "auto_replies": self.auto_replies,
            "forwards": self.forwards,
            "total_confidence": self.total_confidence,
            "total_latency_ms": self.total_latency_ms,
            "channel_counts": {str(k): v for k, v in self.channel_counts.items()},
            "recent": [
                {
                    "question": r.question,
                    "channel_id": r.channel_id,
                    "confidence": r.confidence,
                    "action": r.action,
                    "latency_ms": r.latency_ms,
                    "timestamp": r.timestamp,
                }
                for r in self.recent
            ],
        }
        try:
            atomic_json_write(STATS_FILE, data)
        except OSError as exc:
            logger.warning("Failed to save stats: %s", exc)

    async def start_periodic_save(self) -> None:
        """Start background task that saves stats periodically."""
        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._periodic_save_loop())

    async def stop(self) -> None:
        """Stop periodic save and flush."""
        if self._save_task is not None:
            self._save_task.cancel()
            self._save_task = None
        if self._dirty:
            self._save()
            self._dirty = False

    async def _periodic_save_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(_SAVE_INTERVAL)
                if self._dirty:
                    self._save()
                    self._dirty = False
        except asyncio.CancelledError:
            pass


# Module-level singleton
bot_stats = BotStats()
