"""Tests for bot.chromadb_async module — AsyncCollection wrapper."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from bot.chromadb_async import AsyncCollection


class TestAsyncCollectionDelegation:
    """Verify that AsyncCollection properly delegates to the underlying sync collection."""

    def _make_collection(self):
        col = MagicMock()
        col.query.return_value = {"documents": [["doc1"]], "distances": [[0.1]]}
        col.get.return_value = {"ids": ["id1"]}
        col.count.return_value = 42
        col.add.return_value = None
        col.upsert.return_value = None
        col.delete.return_value = None
        col.update.return_value = None
        return col

    @pytest.mark.asyncio
    async def test_query_delegates(self):
        col = self._make_collection()
        acol = AsyncCollection(col)
        result = await acol.query(query_embeddings=[[0.1, 0.2]], n_results=5)
        col.query.assert_called_once_with(query_embeddings=[[0.1, 0.2]], n_results=5)
        assert result["documents"] == [["doc1"]]

    @pytest.mark.asyncio
    async def test_get_delegates(self):
        col = self._make_collection()
        acol = AsyncCollection(col)
        result = await acol.get(ids=["id1"])
        col.get.assert_called_once_with(ids=["id1"])
        assert result["ids"] == ["id1"]

    @pytest.mark.asyncio
    async def test_count_delegates(self):
        col = self._make_collection()
        acol = AsyncCollection(col)
        result = await acol.count()
        col.count.assert_called_once()
        assert result == 42

    @pytest.mark.asyncio
    async def test_add_delegates(self):
        col = self._make_collection()
        acol = AsyncCollection(col)
        await acol.add(ids=["new"], documents=["text"])
        col.add.assert_called_once_with(ids=["new"], documents=["text"])

    @pytest.mark.asyncio
    async def test_upsert_delegates(self):
        col = self._make_collection()
        acol = AsyncCollection(col)
        await acol.upsert(ids=["id1"], documents=["updated"])
        col.upsert.assert_called_once_with(ids=["id1"], documents=["updated"])

    @pytest.mark.asyncio
    async def test_delete_delegates(self):
        col = self._make_collection()
        acol = AsyncCollection(col)
        await acol.delete(ids=["id1"])
        col.delete.assert_called_once_with(ids=["id1"])

    @pytest.mark.asyncio
    async def test_update_delegates(self):
        col = self._make_collection()
        acol = AsyncCollection(col)
        await acol.update(ids=["id1"], documents=["new doc"])
        col.update.assert_called_once_with(ids=["id1"], documents=["new doc"])
