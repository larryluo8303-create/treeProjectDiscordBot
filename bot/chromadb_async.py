"""Thin async wrapper around ChromaDB's synchronous Collection.

ChromaDB's Python client is synchronous and will block the event loop
when called from ``async`` code.  This wrapper delegates every call to
``asyncio.to_thread`` so the bot's event loop stays responsive.
"""

import asyncio
from typing import Any

import chromadb


class AsyncCollection:
    """Drop-in async wrapper for ``chromadb.Collection``."""

    def __init__(self, collection: chromadb.Collection) -> None:
        self._col = collection

    # ── Read operations ──────────────────────────────────────────────────

    async def query(self, **kwargs: Any) -> dict:
        return await asyncio.to_thread(self._col.query, **kwargs)

    async def get(self, **kwargs: Any) -> dict:
        return await asyncio.to_thread(self._col.get, **kwargs)

    async def count(self) -> int:
        return await asyncio.to_thread(self._col.count)

    # ── Write operations ─────────────────────────────────────────────────

    async def add(self, **kwargs: Any) -> None:
        await asyncio.to_thread(self._col.add, **kwargs)

    async def upsert(self, **kwargs: Any) -> None:
        await asyncio.to_thread(self._col.upsert, **kwargs)

    async def delete(self, **kwargs: Any) -> None:
        await asyncio.to_thread(self._col.delete, **kwargs)

    async def update(self, **kwargs: Any) -> None:
        await asyncio.to_thread(self._col.update, **kwargs)
