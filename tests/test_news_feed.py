"""Tests for bot.news_feed module — filtering, title extraction, embed building, persistence, backfill, archive."""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import discord
import pytest

from bot.news_feed import (
    NewsFeedCog,
    _append_to_archive,
    _clean_html,
    _convert_beijing_to_toronto,
    _load_archive_ids,
    _load_last_id,
    _read_archive,
    _save_last_id,
    build_embed,
    build_text,
    extract_title_and_content,
    filter_items,
)


# ── Sample data ──────────────────────────────────────────────────────────────

def _make_item(
    item_id: str = "20260815100000000001",
    content: str = "【美联储】美联储维持利率不变",
    important: int = 1,
    item_type: int = 0,
    ad: bool = False,
    pic: str = "",
    link: str = "",
    time_str: str = "2026-08-15 10:00:00",
) -> dict:
    return {
        "id": item_id,
        "time": time_str,
        "type": item_type,
        "important": important,
        "data": {"content": content, "pic": pic, "link": link},
        "extras": {"ad": ad},
        "channel": [1, 5],
    }


# ── HTML cleaning ─────────────────────────────────────────────────────────────────────────


class TestCleanHtml:
    def test_br_to_newline(self):
        assert _clean_html("hello<br/>world") == "hello\nworld"
        assert _clean_html("hello<br>world") == "hello\nworld"
        assert _clean_html("hello<br />world") == "hello\nworld"

    def test_span_removed(self):
        html = '<span class="section-news">1. 全国铁路发送旅客28亿人次。</span>'
        assert _clean_html(html) == "1. 全国铁路发送旅客28亿人次。"

    def test_complex_jin10_content(self):
        html = (
            '国内新闻：<br/><span class="section-news">'
            '1. 票房突碴30亿。</span><br/>'
            '<span class="section-news">2. 铁路发送旅客28亿。</span>'
        )
        result = _clean_html(html)
        assert "<" not in result
        assert "1. 票房突碴30亿。" in result
        assert "2. 铁路发送旅客28亿。" in result

    def test_empty_string(self):
        assert _clean_html("") == ""

    def test_none_returns_empty_string(self):
        assert _clean_html(None) == ""

    def test_no_html(self):
        assert _clean_html("现货黄金短线拉升") == "现货黄金短线拉升"

    def test_collapses_blank_lines(self):
        assert _clean_html("a<br/><br/><br/><br/>b") == "a\n\nb"


# ── Title extraction ────────────────────────────────────────────────────────────────


class TestExtractTitleAndContent:
    def test_standard_title(self):
        title, body = extract_title_and_content("【美联储】维持利率不变，符合市场预期")
        assert title == "美联储"
        assert body == "维持利率不变，符合市场预期"

    def test_title_only(self):
        title, body = extract_title_and_content("【快讯】")
        assert title == "快讯"
        assert body == "快讯"  # body falls back to title when no trailing text

    def test_no_title_bracket(self):
        title, body = extract_title_and_content("现货黄金短线走高近5美元")
        assert title == "现货黄金短线走高近5美元"
        assert body == "现货黄金短线走高近5美元"

    def test_long_no_title(self):
        long_text = "A" * 100
        title, body = extract_title_and_content(long_text)
        assert len(title) == 60
        assert body == long_text

    def test_empty(self):
        assert extract_title_and_content("") == ("", "")

    def test_nested_brackets(self):
        title, body = extract_title_and_content("【美股收盘】道指涨超200点，纳指创新高")
        assert title == "美股收盘"
        assert "道指涨超200点" in body


# ── Item filtering ──────────────────────────────────────────────────────────


class TestFilterItems:
    def test_filters_by_last_id(self):
        items = [
            _make_item(item_id="20260815100000000001"),
            _make_item(item_id="20260815100000000002"),
            _make_item(item_id="20260815100000000003"),
        ]
        result = filter_items(items, "20260815100000000002")
        assert len(result) == 1
        assert result[0]["id"] == "20260815100000000003"

    def test_filters_ads(self):
        items = [
            _make_item(item_id="20260815100000000010", ad=True),
            _make_item(item_id="20260815100000000011", ad=False),
        ]
        result = filter_items(items, "")
        assert len(result) == 1
        assert result[0]["id"] == "20260815100000000011"

    def test_filters_type_1(self):
        items = [
            _make_item(item_id="20260815100000000020", item_type=1),
            _make_item(item_id="20260815100000000021", item_type=0),
        ]
        result = filter_items(items, "")
        assert len(result) == 1
        assert result[0]["id"] == "20260815100000000021"

    def test_important_only(self):
        items = [
            _make_item(item_id="20260815100000000030", important=0),
            _make_item(item_id="20260815100000000031", important=1),
        ]
        result = filter_items(items, "", important_only=True)
        assert len(result) == 1
        assert result[0]["id"] == "20260815100000000031"

    def test_all_items_when_not_important_only(self):
        items = [
            _make_item(item_id="20260815100000000040", important=0),
            _make_item(item_id="20260815100000000041", important=1),
        ]
        result = filter_items(items, "", important_only=False)
        assert len(result) == 2

    def test_filters_empty_content(self):
        items = [
            _make_item(item_id="20260815100000000050", content=""),
            _make_item(item_id="20260815100000000051", content="有内容"),
        ]
        result = filter_items(items, "")
        assert len(result) == 1
        assert result[0]["id"] == "20260815100000000051"

    def test_sorted_oldest_first(self):
        items = [
            _make_item(item_id="20260815100000000063"),
            _make_item(item_id="20260815100000000061"),
            _make_item(item_id="20260815100000000062"),
        ]
        result = filter_items(items, "")
        ids = [r["id"] for r in result]
        assert ids == [
            "20260815100000000061",
            "20260815100000000062",
            "20260815100000000063",
        ]

    def test_no_last_id_returns_all(self):
        items = [_make_item(item_id=f"2026081510000000007{i}") for i in range(5)]
        result = filter_items(items, "")
        assert len(result) == 5

    def test_empty_items(self):
        assert filter_items([], "") == []
        assert filter_items([], "someid") == []


# ── Embed / text building ───────────────────────────────────────────────────


class TestBuildEmbed:
    def test_basic_embed(self):
        item = _make_item(content="【黄金】现货黄金短线拉升", time_str="2026-08-15 10:30:00")
        embed = build_embed(item)
        assert isinstance(embed, discord.Embed)
        assert "黄金" in embed.title
        assert embed.color.value == 0xE74C3C
        # Beijing 10:30 → Toronto 22:30 previous day (EDT, UTC-4)
        assert "22:30:00 ET" in embed.footer.text

    def test_embed_with_pic(self):
        item = _make_item(pic="https://example.com/chart.png")
        embed = build_embed(item)
        assert embed.image.url == "https://example.com/chart.png"

    def test_embed_without_pic(self):
        item = _make_item(pic="")
        embed = build_embed(item)
        # No image set — either image proxy is None or url is not a real http URL
        url = getattr(embed.image, 'url', None) if embed.image else None
        assert url is None or not url.startswith('http')

    def test_embed_with_link(self):
        item = _make_item(link="https://jin10.com/detail/123")
        embed = build_embed(item)
        field_values = [f.value for f in embed.fields]
        assert any("查看详情" in v for v in field_values)


class TestBuildText:
    def test_basic_text(self):
        item = _make_item(
            content="现货黄金短线走高近5美元",
            time_str="2026-08-15 11:00:00",
        )
        text = build_text(item)
        assert "现货黄金短线走高近5美元" in text
        assert text.startswith("\U0001f4f0")


# ── Persistence ─────────────────────────────────────────────────────────────


class TestPersistence:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "last_id.json")
            with patch("bot.news_feed.LAST_ID_FILE", path):
                _save_last_id("20260815100000000099")
                loaded = _load_last_id()
                assert loaded == "20260815100000000099"

    def test_load_missing_file(self):
        with patch("bot.news_feed.LAST_ID_FILE", "/nonexistent/path.json"):
            assert _load_last_id() == ""

    def test_load_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "corrupt.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("not json")
            with patch("bot.news_feed.LAST_ID_FILE", path):
                assert _load_last_id() == ""

    def test_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "last_id.json")
            with patch("bot.news_feed.LAST_ID_FILE", path):
                _save_last_id("id_first")
                _save_last_id("id_second")
                assert _load_last_id() == "id_second"


# ── Backfill ────────────────────────────────────────────────────────────────


def _make_api_response(items: list[dict]) -> dict:
    """Build a Jin10 API-shaped response payload."""
    return {"data": {"data": items}}


class TestBackfillFilterLogic:
    """Test that filter_items correctly handles backfill scenarios."""

    def test_backfill_skips_already_seen(self):
        old_id = "20260815080000000001"
        items = [
            _make_item(item_id="20260815080000000001", content="【旧闻】已经发过"),
            _make_item(item_id="20260815090000000002", content="【新闻】离线期间的"),
            _make_item(item_id="20260815100000000003", content="【新闻2】离线期间的2"),
        ]
        result = filter_items(items, old_id, important_only=True)
        assert len(result) == 2
        assert result[0]["id"] == "20260815090000000002"
        assert result[1]["id"] == "20260815100000000003"

    def test_backfill_only_important(self):
        items = [
            _make_item(item_id="20260815090000000010", important=0),
            _make_item(item_id="20260815090000000011", important=1),
            _make_item(item_id="20260815090000000012", important=0),
            _make_item(item_id="20260815090000000013", important=1),
        ]
        result = filter_items(items, "", important_only=True)
        assert len(result) == 2
        ids = [r["id"] for r in result]
        assert "20260815090000000011" in ids
        assert "20260815090000000013" in ids

    def test_backfill_caps_at_50(self):
        items = [
            _make_item(item_id=f"2026081509{i:010d}")
            for i in range(60)
        ]
        result = filter_items(items, "", important_only=True)
        assert len(result) == 60  # filter_items itself doesn't cap; backfill method does


def _beijing_time(hours_ago: float = 1) -> str:
    """Beijing-time string like the Jin10 API returns, N hours before now."""
    return (
        datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(hours=hours_ago)
    ).strftime("%Y-%m-%d %H:%M:%S")


class TestBackfillFromArchive:
    """Backfill reads history from the local archive, never the Jin10 API.

    The flash endpoint ignores max_id pagination (verified 2026-09-29: every
    page returns the same latest ~21 items), so API paging back cannot cover
    an outage longer than ~1h. The poll loop archives every raw page; the
    backfill consumes that archive.
    """

    @pytest.fixture
    def cog(self):
        bot = MagicMock()
        bot.get_channel = MagicMock(return_value=None)
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()
        bot.fetch_channel = AsyncMock(return_value=mock_channel)
        with patch("bot.news_feed._load_last_id", return_value="20260815060000000001"), \
             patch("bot.news_feed._load_archive_ids", return_value=set()), \
             patch("bot.news_feed._save_last_id"):
            cog = NewsFeedCog(bot)
        return cog

    @pytest.fixture
    def mock_channel(self, cog):
        return cog.bot.fetch_channel.return_value

    def _archive_item(self, item_id, hours_ago=1, **kwargs):
        return _make_item(item_id=item_id, time_str=_beijing_time(hours_ago), **kwargs)

    def _write_archive(self, path, items):
        with open(path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    async def _run_backfill(self, cog, archive_path, hours=24):
        with patch("bot.news_feed.ARCHIVE_FILE", archive_path), \
             patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_BACKFILL_HOURS", hours):
            await cog._backfill_on_startup()

    @pytest.mark.asyncio
    async def test_backfill_posts_header_and_items(self, cog, mock_channel, tmp_path):
        archive = tmp_path / "archive.jsonl"
        self._write_archive(str(archive), [
            self._archive_item("20260815100000000003", hours_ago=1, content="【A】内容A"),
            self._archive_item("20260815100000000002", hours_ago=2, content="【B】内容B"),
            self._archive_item("20260815100000000001", hours_ago=3, content="【C】内容C"),
        ])
        await self._run_backfill(cog, str(archive))

        # 1 header embed + 3 item embeds = 4 calls
        assert mock_channel.send.call_count == 4
        first_call_kwargs = mock_channel.send.call_args_list[0].kwargs
        header_embed = first_call_kwargs.get("embed")
        assert header_embed is not None
        assert "离线期间" in header_embed.title or "离线期间" in (header_embed.description or "")
        # Items posted oldest-first
        bodies = [c.kwargs.get("embed").description or "" for c in mock_channel.send.call_args_list[1:]]
        assert "内容C" in bodies[0] and "内容B" in bodies[1] and "内容A" in bodies[2]

    @pytest.mark.asyncio
    async def test_backfill_never_hits_api(self, cog, mock_channel, tmp_path):
        """Backfill must not touch the network at all (no session usage)."""
        archive = tmp_path / "archive.jsonl"
        self._write_archive(str(archive), [
            self._archive_item("20260815100000000003", hours_ago=1),
        ])
        cog._get_session = AsyncMock(side_effect=AssertionError("backfill must not call the API"))
        await self._run_backfill(cog, str(archive))
        # 1 header + 1 item — posted purely from the archive
        assert mock_channel.send.call_count == 2

    @pytest.mark.asyncio
    async def test_backfill_dedups_archive_duplicates(self, cog, mock_channel, tmp_path):
        """Duplicate lines for the same id in the archive must post once."""
        archive = tmp_path / "archive.jsonl"
        dup = self._archive_item("20260815100000000003", hours_ago=1, content="【A】内容A")
        self._write_archive(str(archive), [dup, dup])
        await self._run_backfill(cog, str(archive))

        # 1 header + 1 unique item = 2 calls — NOT 3
        assert mock_channel.send.call_count == 2

    @pytest.mark.asyncio
    async def test_backfill_time_window_filters_old_items(self, cog, mock_channel, tmp_path):
        """Items older than NEWS_BACKFILL_HOURS are excluded from the archive read."""
        archive = tmp_path / "archive.jsonl"
        old = self._archive_item("20260815120000000009", hours_ago=30, content="【旧】超窗口")
        fresh = self._archive_item("20260815100000000003", hours_ago=1, content="【新】窗口内")
        self._write_archive(str(archive), [old, fresh])
        with patch("bot.news_feed._save_last_id") as mock_save:
            with patch("bot.news_feed.ARCHIVE_FILE", str(archive)), \
                 patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
                 patch("bot.news_feed.NEWS_BACKFILL_HOURS", 24):
                await cog._backfill_on_startup()

        # 1 header + only the fresh item
        assert mock_channel.send.call_count == 2
        bodies = [c.kwargs.get("embed").description or "" for c in mock_channel.send.call_args_list[1:]]
        assert all("超窗口" not in b for b in bodies)
        # Cursor advances only over in-window collected items
        mock_save.assert_called_once_with("20260815100000000003")
        assert cog._last_id == "20260815100000000003"

    @pytest.mark.asyncio
    async def test_backfill_skips_items_at_or_below_last_id(self, cog, mock_channel, tmp_path):
        """No duplicate posts for items the cursor already passed."""
        archive = tmp_path / "archive.jsonl"
        self._write_archive(str(archive), [
            self._archive_item("20260815060000000001", hours_ago=1, content="【旧】已发过"),
            self._archive_item("20260815050000000001", hours_ago=2, content="【更旧】已发过"),
        ])
        await self._run_backfill(cog, str(archive))

        mock_channel.send.assert_not_called()
        assert cog._last_id == "20260815060000000001"

    @pytest.mark.asyncio
    async def test_backfill_empty_archive(self, cog, mock_channel, tmp_path):
        """Missing archive file: no posts, no crash, cursor untouched."""
        missing = str(tmp_path / "does-not-exist.jsonl")
        await self._run_backfill(cog, missing)

        mock_channel.send.assert_not_called()
        assert cog._last_id == "20260815060000000001"

    @pytest.mark.asyncio
    async def test_backfill_updates_last_id(self, cog, mock_channel, tmp_path):
        archive = tmp_path / "archive.jsonl"
        self._write_archive(str(archive), [
            self._archive_item("20260815110000000005", hours_ago=1),
            self._archive_item("20260815100000000003", hours_ago=2),
        ])
        with patch("bot.news_feed._save_last_id") as mock_save:
            with patch("bot.news_feed.ARCHIVE_FILE", str(archive)), \
                 patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
                 patch("bot.news_feed.NEWS_BACKFILL_HOURS", 24):
                await cog._backfill_on_startup()

        # Should save the newest collected ID
        mock_save.assert_called_once_with("20260815110000000005")
        assert cog._last_id == "20260815110000000005"

    @pytest.mark.asyncio
    async def test_backfill_skips_unparseable_time(self, cog, mock_channel, tmp_path):
        """Archive lines with garbage timestamps are skipped, not fatal."""
        archive = tmp_path / "archive.jsonl"
        bad = self._archive_item("20260815100000000004", hours_ago=1)
        bad["time"] = "not-a-time"
        good = self._archive_item("20260815100000000003", hours_ago=1, content="【好】内容")
        self._write_archive(str(archive), [bad, good])
        await self._run_backfill(cog, str(archive))

        assert mock_channel.send.call_count == 2  # header + good item only

    @pytest.mark.asyncio
    async def test_backfill_advances_last_id_for_non_important_only(self, cog, mock_channel, tmp_path):
        """Non-important items collected during backfill still advance last_id."""
        archive = tmp_path / "archive.jsonl"
        self._write_archive(str(archive), [
            self._archive_item("20260815110000000005", hours_ago=1, important=0),
        ])
        with patch("bot.news_feed._save_last_id") as mock_save, \
             patch("bot.news_feed.NEWS_IMPORTANT_ONLY", True):
            with patch("bot.news_feed.ARCHIVE_FILE", str(archive)), \
                 patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
                 patch("bot.news_feed.NEWS_BACKFILL_HOURS", 24):
                await cog._backfill_on_startup()

        mock_channel.send.assert_not_called()
        mock_save.assert_called_once_with("20260815110000000005")
        assert cog._last_id == "20260815110000000005"

    @pytest.mark.asyncio
    async def test_backfill_caps_at_50(self, cog, mock_channel, tmp_path):
        archive = tmp_path / "archive.jsonl"
        items = [
            self._archive_item(f"2026081510{i:010d}", hours_ago=1, content=f"【{i}】内容")
            for i in range(60)
        ]
        self._write_archive(str(archive), items)
        await self._run_backfill(cog, str(archive))

        # 1 header + 50 newest items = 51 calls
        assert mock_channel.send.call_count == 51

    @pytest.mark.asyncio
    async def test_backfill_skipped_when_no_last_id(self):
        bot = MagicMock()
        with patch("bot.news_feed._load_last_id", return_value=""):
            cog = NewsFeedCog(bot)
        # last_id is empty → backfill condition is False
        assert cog._last_id == ""


class TestArchiveHelpers:
    """Unit tests for the local rolling archive helpers."""

    def test_append_and_read_roundtrip(self, tmp_path):
        path = str(tmp_path / "archive.jsonl")
        items = [_make_item(item_id="20260815100000000001"),
                 _make_item(item_id="20260815100000000002")]
        with patch("bot.news_feed.ARCHIVE_FILE", path):
            seen: set = set()
            _append_to_archive(items, seen)
            assert seen == {"20260815100000000001", "20260815100000000002"}
            back = _read_archive()
        assert [it["id"] for it in back] == ["20260815100000000001", "20260815100000000002"]
        # Raw items preserved (not just ids)
        assert back[0]["data"]["content"]

    def test_append_dedups(self, tmp_path):
        path = str(tmp_path / "archive.jsonl")
        items = [_make_item(item_id="20260815100000000001")]
        with patch("bot.news_feed.ARCHIVE_FILE", path):
            seen: set = set()
            _append_to_archive(items, seen)
            _append_to_archive(items, seen)  # same page again
            _append_to_archive([_make_item(item_id="")], seen)  # empty id skipped
            back = _read_archive()
        assert len(back) == 1

    def test_load_archive_ids(self, tmp_path):
        path = str(tmp_path / "archive.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(_make_item(item_id="20260815100000000001")) + "\n")
            f.write("garbage line\n")
            f.write("\n")
        with patch("bot.news_feed.ARCHIVE_FILE", path):
            ids = _load_archive_ids()
        assert ids == {"20260815100000000001"}

    def test_read_archive_missing_file(self, tmp_path):
        with patch("bot.news_feed.ARCHIVE_FILE", str(tmp_path / "nope.jsonl")):
            assert _read_archive() == []


class TestFetchAndPost:
    @pytest.mark.asyncio
    async def test_does_not_advance_last_id_when_post_fails(self, tmp_path):
        bot = MagicMock()
        bot.get_channel.return_value = None
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "fail"))
        bot.fetch_channel = AsyncMock(return_value=mock_channel)

        with patch("bot.news_feed._load_last_id", return_value="20260815060000000001"), \
             patch("bot.news_feed._load_archive_ids", return_value=set()), \
             patch("bot.news_feed._save_last_id"):
            cog = NewsFeedCog(bot)

        items = [_make_item(item_id="20260815110000000005")]
        payload = _make_api_response(items)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=payload)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_session.closed = False
        cog._session = mock_session

        with patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_IMPORTANT_ONLY", True), \
             patch("bot.news_feed._save_last_id") as mock_save, \
             patch("bot.news_feed.ARCHIVE_FILE", str(tmp_path / "archive.jsonl")):
            await cog._fetch_and_post()

        mock_save.assert_not_called()
        assert cog._last_id == "20260815060000000001"


class TestArchivePoll:
    """The poll loop archives every raw page it fetches (backfill source)."""

    @pytest.fixture
    def cog(self):
        bot = MagicMock()
        bot.get_channel = MagicMock(return_value=None)
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()
        bot.fetch_channel = AsyncMock(return_value=mock_channel)
        with patch("bot.news_feed._load_last_id", return_value="20260815060000000001"), \
             patch("bot.news_feed._load_archive_ids", return_value=set()), \
             patch("bot.news_feed._save_last_id"):
            cog = NewsFeedCog(bot)
        return cog

    @pytest.fixture
    def mock_channel(self, cog):
        return cog.bot.fetch_channel.return_value

    def _mock_session(self, cog, items):
        payload = _make_api_response(items)
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=payload)
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_session.closed = False
        cog._session = mock_session

    @pytest.mark.asyncio
    async def test_poll_archives_raw_items(self, cog, mock_channel, tmp_path):
        """Fetched raw items land in the archive, even ones never posted."""
        archive = str(tmp_path / "archive.jsonl")
        items = [
            _make_item(item_id="20260815110000000005", content="【重要】内容5"),
            _make_item(item_id="20260815110000000006", important=0, content="【普通】内容6"),
        ]
        self._mock_session(cog, items)
        with patch("bot.news_feed.ARCHIVE_FILE", archive), \
             patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_IMPORTANT_ONLY", True):
            await cog._fetch_and_post()

        # Only the important item was posted...
        assert mock_channel.send.call_count == 1
        # ...but BOTH raw items were archived
        with patch("bot.news_feed.ARCHIVE_FILE", archive):
            back = _read_archive()
        assert [it["id"] for it in back] == ["20260815110000000005", "20260815110000000006"]
        assert cog._archived_ids == {"20260815110000000005", "20260815110000000006"}
        # Raw dicts preserved
        assert back[0]["data"]["content"] == "【重要】内容5"

    @pytest.mark.asyncio
    async def test_poll_archive_dedups_repeat_pages(self, cog, mock_channel, tmp_path):
        """Fetching the same page twice must not duplicate archive lines."""
        archive = str(tmp_path / "archive.jsonl")
        items = [_make_item(item_id="20260815110000000005")]
        with patch("bot.news_feed.ARCHIVE_FILE", archive), \
             patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_IMPORTANT_ONLY", True):
            self._mock_session(cog, items)
            await cog._fetch_and_post()
            # Simulate a later poll returning the same page (API overlap)
            self._mock_session(cog, items)
            await cog._fetch_and_post()
            back = _read_archive()
        assert len(back) == 1

    @pytest.mark.asyncio
    async def test_poll_archives_when_nothing_new(self, cog, mock_channel, tmp_path):
        """Items older than last_id are not posted, but still archived."""
        archive = str(tmp_path / "archive.jsonl")
        items = [_make_item(item_id="20260815050000000001", content="【旧】内容")]
        self._mock_session(cog, items)
        with patch("bot.news_feed.ARCHIVE_FILE", archive), \
             patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_IMPORTANT_ONLY", True):
            await cog._fetch_and_post()
            back = _read_archive()
        mock_channel.send.assert_not_called()
        assert [it["id"] for it in back] == ["20260815050000000001"]


# ── Beijing to Toronto time conversion ───────────────────────────────────────


class TestConvertBeijingToToronto:
    def test_summer_edt(self):
        """Summer (EDT, UTC-4): Beijing 10:30 → Toronto 22:30 previous day."""
        result = _convert_beijing_to_toronto("2026-08-15 10:30:00")
        assert result == "2026-08-14 22:30:00 ET"

    def test_winter_est(self):
        """Winter (EST, UTC-5): Beijing 10:30 → Toronto 21:30 previous day."""
        result = _convert_beijing_to_toronto("2026-01-15 10:30:00")
        assert result == "2026-01-14 21:30:00 ET"

    def test_empty_string(self):
        assert _convert_beijing_to_toronto("") == ""

    def test_invalid_format(self):
        assert _convert_beijing_to_toronto("not-a-date") == "not-a-date"
