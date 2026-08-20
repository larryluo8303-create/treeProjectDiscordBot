"""In-memory review queue with JSON persistence.

Stores pending review items that can be accessed from the mobile/web app
as an alternative to (or alongside) the Discord DM review flow.
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

REVIEW_QUEUE_FILE = data_path(os.getenv("REVIEW_QUEUE_FILE", "data/review_queue.json"))


@dataclass
class ReviewItem:
    id: str
    channel_id: int
    channel_name: str
    message_id: int
    author_name: str
    author_id: int
    question: str
    draft_answer: str
    confidence: int
    context_snippets: list[dict]
    created_at: float
    status: str = "pending"  # pending | approved | edited | rejected
    final_answer: str = ""
    reviewed_at: float = 0.0
    jump_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewItem":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ReviewQueue:
    """Thread-safe review queue with persistence."""

    def __init__(self) -> None:
        self._items: dict[str, ReviewItem] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(REVIEW_QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item_dict in data:
                item = ReviewItem.from_dict(item_dict)
                self._items[item.id] = item
            logger.info("Loaded %d review queue items", len(self._items))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        try:
            items = [item.to_dict() for item in self._items.values()]
            atomic_json_write(REVIEW_QUEUE_FILE, items, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("Failed to save review queue: %s", exc)

    def add(
        self,
        channel_id: int,
        channel_name: str,
        message_id: int,
        author_name: str,
        author_id: int,
        question: str,
        draft_answer: str,
        confidence: int,
        context_snippets: list[dict] | None = None,
        jump_url: str = "",
    ) -> ReviewItem:
        """Add a new item to the review queue."""
        item = ReviewItem(
            id=str(uuid.uuid4())[:8],
            channel_id=channel_id,
            channel_name=channel_name,
            message_id=message_id,
            author_name=author_name,
            author_id=author_id,
            question=question[:2000],
            draft_answer=draft_answer[:4000],
            confidence=confidence,
            context_snippets=context_snippets[:3] if context_snippets else [],
            created_at=time.time(),
            jump_url=jump_url,
        )
        self._items[item.id] = item
        self._save()
        logger.info("Review queue: added item %s (confidence=%d)", item.id, confidence)
        return item

    def get_pending(self) -> list[ReviewItem]:
        """Return all pending items, newest first."""
        return sorted(
            [i for i in self._items.values() if i.status == "pending"],
            key=lambda i: i.created_at,
            reverse=True,
        )

    def get_all(self, limit: int = 50) -> list[ReviewItem]:
        """Return all items (any status), newest first."""
        items = sorted(self._items.values(), key=lambda i: i.created_at, reverse=True)
        return items[:limit]

    def get(self, item_id: str) -> ReviewItem | None:
        return self._items.get(item_id)

    def approve(self, item_id: str) -> ReviewItem | None:
        item = self._items.get(item_id)
        if item and item.status == "pending":
            item.status = "approved"
            item.final_answer = item.draft_answer
            item.reviewed_at = time.time()
            self._save()
            return item
        return None

    def edit(self, item_id: str, edited_answer: str) -> ReviewItem | None:
        item = self._items.get(item_id)
        if item and item.status == "pending":
            item.status = "edited"
            item.final_answer = edited_answer
            item.reviewed_at = time.time()
            self._save()
            return item
        return None

    def reject(self, item_id: str) -> ReviewItem | None:
        item = self._items.get(item_id)
        if item and item.status == "pending":
            item.status = "rejected"
            item.reviewed_at = time.time()
            self._save()
            return item
        return None

    @property
    def pending_count(self) -> int:
        return sum(1 for i in self._items.values() if i.status == "pending")


# Singleton
review_queue = ReviewQueue()
