"""Tests for bot.news_feed module — filtering, title extraction, embed building, persistence, backfill."""

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.news_feed import (
    NewsFeedCog,
    _BACKFILL_MAX_PAGES,
    _clean_html,
    _convert_beijing_to_toronto,
    _load_last_id,
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


class TestBackfillIntegration:
    """Integration tests for _backfill_on_startup using mocked HTTP + Discord."""

    # Test items use 2026-08-15 timestamps; use a wide window so tests stay stable.
    _BACKFILL_HOURS = 8760

    @pytest.fixture
    def cog(self):
        bot = MagicMock()
        bot.get_channel = MagicMock(return_value=None)
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()
        bot.fetch_channel = AsyncMock(return_value=mock_channel)
        with patch("bot.news_feed._load_last_id", return_value="20260815060000000001"):
            cog = NewsFeedCog(bot)
        return cog

    @pytest.fixture
    def mock_channel(self, cog):
        return cog.bot.fetch_channel.return_value

    def _make_page(self, id_prefix: str, count: int = 5, time_str: str = "2026-08-15 10:00:00"):
        """Create a page of items for mock API response."""
        items = [
            _make_item(
                item_id=f"{id_prefix}{i:06d}",
                content=f"【快讯{i}】内容{i}",
                time_str=time_str,
            )
            for i in range(count)
        ]
        return _make_api_response(items)

    @pytest.mark.asyncio
    async def test_backfill_posts_header_and_items(self, cog, mock_channel):
        page = self._make_page("20260815100000", count=3, time_str="2026-08-15 10:00:00")
        empty_page = _make_api_response([])

        # First call returns items, second returns empty to stop pagination
        responses = iter([page, empty_page])

        async def _json_side_effect(content_type=None):
            return next(responses)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = _json_side_effect

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_session.closed = False
        cog._session = mock_session

        with patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_BACKFILL_HOURS", self._BACKFILL_HOURS):
            await cog._backfill_on_startup()

        # 1 header embed + 3 item embeds = 4 calls
        assert mock_channel.send.call_count == 4
        # First call is the header
        first_call_kwargs = mock_channel.send.call_args_list[0].kwargs
        header_embed = first_call_kwargs.get("embed")
        assert header_embed is not None
        assert "离线期间" in header_embed.title or "离线期间" in (header_embed.description or "")

    @pytest.mark.asyncio
    async def test_backfill_dedup_across_pages(self, cog, mock_channel):
        """Regression: pagination overlap must not cause duplicate posts."""
        # Page 1: items A, B, C (C is oldest, used as max_id for page 2)
        # Page 2: items C, D (C overlaps with page 1) then stop
        page1 = _make_api_response([
            _make_item(item_id="20260815100000000003", content="【A】内容A", time_str="2026-08-15 10:00:03"),
            _make_item(item_id="20260815100000000002", content="【B】内容B", time_str="2026-08-15 10:00:02"),
            _make_item(item_id="20260815100000000001", content="【C】内容C", time_str="2026-08-15 10:00:01"),
        ])
        page2 = _make_api_response([
            _make_item(item_id="20260815100000000001", content="【C】内容C", time_str="2026-08-15 10:00:01"),  # overlap
            _make_item(item_id="20260815090000000005", content="【D】内容D", time_str="2026-08-15 09:00:05"),
        ])
        empty_page = _make_api_response([])
        responses = iter([page1, page2, empty_page])

        async def _json_side_effect(content_type=None):
            return next(responses)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = _json_side_effect

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_session.closed = False
        cog._session = mock_session

        with patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_BACKFILL_HOURS", self._BACKFILL_HOURS):
            await cog._backfill_on_startup()

        # 1 header + 4 unique items (A, B, C, D) = 5 calls — NOT 6
        assert mock_channel.send.call_count == 5

    @pytest.mark.asyncio
    async def test_backfill_no_missed_items(self, cog, mock_channel):
        # Return items that are all older than last_id
        items = [
            _make_item(
                item_id="20260815050000000001",
                time_str="2026-08-15 05:00:00",
            )
        ]
        page = _make_api_response(items)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=page)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_session.closed = False
        cog._session = mock_session

        with patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_BACKFILL_HOURS", self._BACKFILL_HOURS):
            await cog._backfill_on_startup()

        # No items should be posted
        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_backfill_updates_last_id(self, cog, mock_channel):
        items = [
            _make_item(item_id="20260815110000000005", time_str="2026-08-15 11:00:00"),
            _make_item(item_id="20260815100000000003", time_str="2026-08-15 10:00:00"),
        ]
        page = _make_api_response(items)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=page)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_session.closed = False
        cog._session = mock_session

        with patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_BACKFILL_HOURS", self._BACKFILL_HOURS), \
             patch("bot.news_feed._save_last_id") as mock_save:
            await cog._backfill_on_startup()

        # Should save the newest ID
        mock_save.assert_called_once_with("20260815110000000005")
        assert cog._last_id == "20260815110000000005"

    @pytest.mark.asyncio
    async def test_backfill_api_error_handled(self, cog, mock_channel):
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.json = AsyncMock(return_value={})

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_session.closed = False
        cog._session = mock_session

        with patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_BACKFILL_HOURS", self._BACKFILL_HOURS):
            # Should not raise
            await cog._backfill_on_startup()

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_backfill_skipped_when_no_last_id(self):
        bot = MagicMock()
        with patch("bot.news_feed._load_last_id", return_value=""):
            cog = NewsFeedCog(bot)
        # last_id is empty → backfill condition is False
        assert cog._last_id == ""

    @pytest.mark.asyncio
    async def test_backfill_advances_last_id_for_non_important_only(self, cog, mock_channel):
        """Non-important items collected during backfill should still advance last_id."""
        items = [
            _make_item(item_id="20260815110000000005", important=0, time_str="2026-08-15 11:00:00"),
        ]
        page = _make_api_response(items)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=page)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        mock_session.closed = False
        cog._session = mock_session

        with patch("bot.news_feed.NEWS_CHANNEL_IDS", [123456]), \
             patch("bot.news_feed.NEWS_BACKFILL_HOURS", self._BACKFILL_HOURS), \
             patch("bot.news_feed.NEWS_IMPORTANT_ONLY", True), \
             patch("bot.news_feed._save_last_id") as mock_save:
            await cog._backfill_on_startup()

        mock_channel.send.assert_not_called()
        mock_save.assert_called_once_with("20260815110000000005")
        assert cog._last_id == "20260815110000000005"


class TestFetchAndPost:
    @pytest.mark.asyncio
    async def test_does_not_advance_last_id_when_post_fails(self):
        bot = MagicMock()
        bot.get_channel.return_value = None
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "fail"))
        bot.fetch_channel = AsyncMock(return_value=mock_channel)

        with patch("bot.news_feed._load_last_id", return_value="20260815060000000001"):
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
             patch("bot.news_feed._save_last_id") as mock_save:
            await cog._fetch_and_post()

        mock_save.assert_not_called()
        assert cog._last_id == "20260815060000000001"


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
