"""Tests for /views helpers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


class TestViewsHelpers:
    def test_clamp_hours(self):
        from bot.views_summary import clamp_views_hours
        assert clamp_views_hours(0) == 1
        assert clamp_views_hours(24) == 24
        assert clamp_views_hours(999) == 168

    def test_history_limit(self):
        from bot.views_summary import history_limit_for_hours
        assert history_limit_for_hours(24) == 200
        assert history_limit_for_hours(168) == 1344
        assert 200 <= history_limit_for_hours(1) <= 1500

    def test_guild_scan_limit(self):
        from bot.views_summary import guild_scan_limit_for_hours, owner_cap_for_hours
        assert guild_scan_limit_for_hours(24) == 400
        assert guild_scan_limit_for_hours(168) == 1500
        assert owner_cap_for_hours(24) == 24
        assert owner_cap_for_hours(1) == 20
        assert owner_cap_for_hours(168) == 50

    def test_guild_text_target(self):
        from bot.views_summary import is_guild_text_target
        guild = MagicMock(spec=discord.Guild)
        text = MagicMock(spec=discord.TextChannel)
        thread = MagicMock(spec=discord.Thread)
        assert is_guild_text_target(text, guild) is True
        assert is_guild_text_target(thread, guild) is True
        assert is_guild_text_target(text, None) is False
        assert is_guild_text_target(None, guild) is False


def _msg(author_id: int, content: str, hour: int, *, bot: bool = False):
    msg = MagicMock()
    msg.author.id = author_id
    msg.author.bot = bot
    msg.author.display_name = f"user{author_id}"
    msg.content = content
    msg.created_at = datetime(2026, 8, 18, hour, 0, tzinfo=timezone.utc)
    msg.reference = None
    return msg


class TestCollectVisibleDms:
    @pytest.mark.asyncio
    async def test_group_dm_includes_both_sides(self, tmp_path):
        from bot.views_summary import collect_visible_dm_conversations

        owner_id = 111
        other = MagicMock()
        other.id = 222
        other.display_name = "MemberA"

        owner_user = MagicMock()
        owner_user.id = owner_id
        owner_user.display_name = "Owner"

        owner_msg = _msg(owner_id, "我看多头", 12)
        other_msg = _msg(222, "能不能买", 11)

        group = MagicMock(spec=discord.GroupChannel)
        group.id = 99
        group.recipients = [owner_user, other]

        async def history(**kwargs):
            for m in (other_msg, owner_msg):
                yield m

        group.history = history

        bot = MagicMock()
        bot.private_channels = [group]
        bot.get_channel = MagicMock(return_value=None)

        since = datetime(2026, 8, 18, tzinfo=timezone.utc)
        dm_file = tmp_path / "dms.json"
        with patch("bot.views_summary._DM_CHANNELS_FILE", str(dm_file)), \
             patch("bot.views_summary.load_private_channel_ids", return_value=[]):
            result = await collect_visible_dm_conversations(bot, owner_id, since)

        kinds = {row["kind"] for row in result}
        contents = [row["content"] for row in result]
        assert "私信" in kinds
        assert "私信对方" in kinds
        assert any("我看多头" in c for c in contents)
        assert any("成员问: 能不能买" in c for c in contents)
        assert not any("MemberA" in c for c in contents)

    @pytest.mark.asyncio
    async def test_skips_bot_member_dms_without_owner(self, tmp_path):
        from bot.views_summary import collect_visible_dm_conversations

        owner_id = 111
        member = MagicMock()
        member.id = 222
        member.display_name = "MemberA"

        member_msg = _msg(222, "请问怎么订阅", 11)

        dm = MagicMock(spec=discord.DMChannel)
        dm.id = 88
        dm.recipient = member

        async def history(**kwargs):
            yield member_msg

        dm.history = history

        bot = MagicMock()
        bot.private_channels = [dm]
        bot.get_channel = MagicMock(return_value=None)

        since = datetime(2026, 8, 18, tzinfo=timezone.utc)
        dm_file = tmp_path / "dms.json"
        with patch("bot.views_summary._DM_CHANNELS_FILE", str(dm_file)), \
             patch("bot.views_summary.load_private_channel_ids", return_value=[]):
            result = await collect_visible_dm_conversations(bot, owner_id, since)

        assert result == []


class TestPrivateThreadConversation:
    @pytest.mark.asyncio
    async def test_private_thread_includes_other_person(self):
        from bot.views_summary import collect_private_thread_messages

        owner_id = 111
        thread = MagicMock(spec=discord.Thread)
        thread.id = 501
        thread.name = "跟进-MemberA"
        thread.type = discord.ChannelType.private_thread

        owner_msg = _msg(owner_id, "建议先观察", 12)
        other_msg = _msg(222, "还能加仓吗", 11)

        async def history(**kwargs):
            for m in (other_msg, owner_msg):
                yield m

        thread.history = history

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 1
        channel.threads = [thread]

        async def empty_archived(**kwargs):
            if False:
                yield None

        channel.archived_threads = empty_archived

        bot = MagicMock()
        result = await collect_private_thread_messages(
            bot, channel, owner_id, datetime(2026, 8, 18, tzinfo=timezone.utc), 200,
        )
        kinds = {row["kind"] for row in result}
        assert "私密帖" in kinds
        assert "私密帖对方" in kinds

    @pytest.mark.asyncio
    async def test_skips_private_thread_without_owner(self):
        from bot.views_summary import collect_private_thread_messages

        owner_id = 111
        thread = MagicMock(spec=discord.Thread)
        thread.id = 502
        thread.name = "别人的帖"
        thread.type = discord.ChannelType.private_thread

        other_msg = _msg(222, "只有我在说话", 11)

        async def history(**kwargs):
            yield other_msg

        thread.history = history

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 1
        channel.threads = [thread]

        async def empty_archived(**kwargs):
            if False:
                yield None

        channel.archived_threads = empty_archived

        bot = MagicMock()
        result = await collect_private_thread_messages(
            bot, channel, owner_id, datetime(2026, 8, 18, tzinfo=timezone.utc), 200,
        )
        assert result == []


class TestFormatKind:
    def test_dm_kind_prefix(self):
        from bot.weekly_summary import format_messages_for_gpt
        text = format_messages_for_gpt([{
            "channel": "私信群:Bob",
            "time": "08/18 12:00",
            "content": "看多",
            "is_reply": True,
            "kind": "私信",
        }])
        assert "[私信]" in text
        assert "看多" in text


class TestViewsSummaryOutput:
    @pytest.mark.asyncio
    async def test_truncates_long_summary(self):
        from bot.views_summary import _VIEWS_MAX_CHARS, generate_views_summary

        long_text = "x" * (_VIEWS_MAX_CHARS + 500)
        with patch("bot.views_summary._openai_chat_with_retry", new=AsyncMock(return_value=long_text)):
            result = await generate_views_summary(MagicMock(), "input")

        assert result is not None
        assert len(result) <= _VIEWS_MAX_CHARS
        assert result.endswith("…")

    @pytest.mark.asyncio
    async def test_whitespace_summary_is_none(self):
        from bot.views_summary import generate_views_summary
        with patch("bot.views_summary._openai_chat_with_retry", new=AsyncMock(return_value="   ")):
            result = await generate_views_summary(MagicMock(), "input")
        assert result is None


class TestRememberOwnerPrivateChannel:
    def test_skips_member_bot_dm(self, tmp_path):
        from bot.views_summary import load_private_channel_ids, remember_owner_private_channel

        dm_file = tmp_path / "dms.json"
        owner_id = 111
        member_dm = MagicMock(spec=discord.DMChannel)
        member_dm.id = 1
        member_dm.recipient = MagicMock(id=222)
        member_msg = MagicMock()
        member_msg.channel = member_dm
        member_msg.author.id = 222

        with patch("bot.views_summary._DM_CHANNELS_FILE", str(dm_file)), \
             patch("bot.views_summary.OWNER_USER_ID", owner_id):
            remember_owner_private_channel(member_msg)
            assert load_private_channel_ids() == []

    def test_keeps_owner_bot_dm(self, tmp_path):
        from bot.views_summary import load_private_channel_ids, remember_owner_private_channel

        dm_file = tmp_path / "dms.json"
        owner_id = 111
        owner_dm = MagicMock(spec=discord.DMChannel)
        owner_dm.id = 2
        owner_dm.recipient = MagicMock(id=owner_id)
        msg = MagicMock()
        msg.channel = owner_dm
        msg.author.id = 999

        with patch("bot.views_summary._DM_CHANNELS_FILE", str(dm_file)), \
             patch("bot.views_summary.OWNER_USER_ID", owner_id):
            remember_owner_private_channel(msg)
            assert load_private_channel_ids() == [2]


class TestGatherCurrentPrivateThread:
    @pytest.mark.asyncio
    async def test_includes_other_person_in_current_private_thread(self):
        from bot.views_summary import gather_views_messages

        owner_id = 111
        thread = MagicMock(spec=discord.Thread)
        thread.id = 501
        thread.name = "跟进"
        thread.type = discord.ChannelType.private_thread
        thread.guild = None
        thread.parent = None

        owner_msg = _msg(owner_id, "建议先观察", 12)
        other_msg = _msg(222, "还能加仓吗", 11)

        async def history(**kwargs):
            for m in (other_msg, owner_msg):
                yield m

        thread.history = history
        bot = MagicMock()
        bot.private_channels = []
        bot.get_channel = MagicMock(return_value=None)

        with patch("bot.views_summary.OWNER_USER_ID", owner_id), \
             patch("bot.views_summary.load_private_channel_ids", return_value=[]):
            messages, _note = await gather_views_messages(bot, thread, 24, include_dms=False)

        kinds = {m["kind"] for m in messages}
        assert "私密帖" in kinds
        assert "私密帖对方" in kinds
        assert any("成员问: 还能加仓吗" in m["content"] for m in messages)
        assert not any("user222" in m["content"] for m in messages)


async def _empty_archived(**kwargs):
    if False:
        yield None


class TestGuildWideScan:
    def test_lists_all_text_channels_skips_excluded(self):
        from bot.views_summary import list_guild_readable_channels

        keep = MagicMock(spec=discord.TextChannel)
        keep.id = 10
        skip = MagicMock(spec=discord.TextChannel)
        skip.id = 99
        voice = MagicMock(spec=discord.VoiceChannel)
        voice.id = 11
        guild = MagicMock(spec=discord.Guild)
        guild.channels = [keep, skip, voice]

        with patch("bot.views_summary.EXCLUDED_CHANNEL_IDS", [99]), \
             patch("bot.views_summary.PROMO_SOURCE_CHANNEL_ID", 0):
            result = list_guild_readable_channels(guild)

        assert [c.id for c in result] == [10]

    @pytest.mark.asyncio
    async def test_gather_scans_every_guild_text_channel(self):
        from bot.views_summary import gather_views_messages

        owner_id = 111
        ch1 = MagicMock(spec=discord.TextChannel)
        ch1.id = 1
        ch1.name = "tech"
        ch1.threads = []
        ch1.archived_threads = _empty_archived

        ch2 = MagicMock(spec=discord.TextChannel)
        ch2.id = 2
        ch2.name = "general"
        ch2.threads = []
        ch2.archived_threads = _empty_archived

        guild = MagicMock(spec=discord.Guild)
        guild.channels = [ch1, ch2]
        guild.active_threads = AsyncMock(return_value=[])
        ch1.guild = guild
        ch2.guild = guild

        bot = MagicMock()
        bot.private_channels = []
        bot.get_channel = MagicMock(return_value=None)

        async def fake_collect(bot_arg, channel_ids, owner_id_arg, since, owner_cap=40, scan_cap=1500):
            return [{
                "channel": str(cid),
                "time": "08/18 12:00",
                "content": f"view-{cid}",
                "is_reply": False,
            } for cid in channel_ids]

        with patch("bot.views_summary.OWNER_USER_ID", owner_id), \
             patch("bot.views_summary.EXCLUDED_CHANNEL_IDS", []), \
             patch("bot.views_summary.PROMO_SOURCE_CHANNEL_ID", 0), \
             patch("bot.views_summary.collect_owner_messages_in_window", new=fake_collect):
            messages, note = await gather_views_messages(bot, ch1, 24, include_dms=False)

        contents = [m["content"] for m in messages]
        assert "view-1" in contents
        assert "view-2" in contents
        assert "已扫描本服务器全部文字频道" in note

    @pytest.mark.asyncio
    async def test_forum_archived_threads_omits_private_kwarg(self):
        from bot.views_summary import collect_guild_owner_messages

        calls: list[dict] = []

        async def archived(**kwargs):
            calls.append(kwargs)
            if False:
                yield None

        forum = MagicMock(spec=discord.ForumChannel)
        forum.id = 5
        forum.threads = []
        forum.archived_threads = archived

        guild = MagicMock(spec=discord.Guild)
        guild.channels = [forum]
        guild.active_threads = AsyncMock(return_value=[])

        async def fake_collect(*args, **kwargs):
            return []

        with patch("bot.views_summary.EXCLUDED_CHANNEL_IDS", []), \
             patch("bot.views_summary.PROMO_SOURCE_CHANNEL_ID", 0), \
             patch("bot.views_summary.collect_owner_messages_in_window", new=fake_collect):
            await collect_guild_owner_messages(
                MagicMock(), guild, 111, datetime(2026, 8, 18, tzinfo=timezone.utc),
                owner_cap=20, scan_cap=400,
            )

        assert calls
        assert "private" not in calls[0]


class TestWindowWalkAndPrivacy:
    @pytest.mark.asyncio
    async def test_finds_owner_after_member_flood(self):
        from bot.views_summary import collect_owner_messages_in_window

        owner_id = 111
        since = datetime(2026, 8, 18, tzinfo=timezone.utc)
        floods = [_msg(222, f"n{i}", 20) for i in range(250)]
        owner = _msg(owner_id, "核心观点看多", 1)
        channel = MagicMock()
        channel.id = 7
        channel.name = "busy"

        async def history(**kwargs):
            assert kwargs.get("oldest_first") is False
            assert kwargs.get("after") is None
            for m in (*floods, owner):
                yield m

        channel.history = history
        bot = MagicMock()
        bot.get_channel.return_value = channel

        result = await collect_owner_messages_in_window(
            bot, [7], owner_id, since, owner_cap=20, scan_cap=1500,
        )
        assert len(result) == 1
        assert result[0]["content"] == "核心观点看多"

    @pytest.mark.asyncio
    async def test_reply_context_hides_member_name(self):
        from bot.views_summary import collect_owner_messages_in_window

        owner_id = 111
        original = MagicMock()
        original.content = "能不能加仓"
        original.author.display_name = "Alice"
        ref = MagicMock()
        ref.message_id = 99
        ref.resolved = original
        owner_msg = _msg(owner_id, "先观察", 12)
        owner_msg.reference = ref

        channel = MagicMock()
        channel.id = 8
        channel.name = "tech"

        async def history(**kwargs):
            yield owner_msg

        channel.history = history
        bot = MagicMock()
        bot.get_channel.return_value = channel

        result = await collect_owner_messages_in_window(
            bot, [8], owner_id, datetime(2026, 8, 18, tzinfo=timezone.utc),
        )
        assert len(result) == 1
        assert "Alice" not in result[0]["content"]
        assert "回复成员" in result[0]["content"]
        assert "先观察" in result[0]["content"]

    def test_count_owner_rows_skips_other_party(self):
        from bot.views_summary import count_owner_view_rows
        rows = [
            {"kind": None, "content": "a"},
            {"kind": "私密帖", "content": "b"},
            {"kind": "私密帖对方", "content": "c"},
            {"kind": "私信对方", "content": "d"},
        ]
        assert count_owner_view_rows(rows) == 2
