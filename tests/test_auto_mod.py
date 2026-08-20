"""Tests for bot.auto_mod — spam / scam / ad detection and auto-delete."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.auto_mod import (
    AutoModCog,
    _DISCORD_INVITE,
    _EXTERNAL_PLATFORM_LINKS,
    _SPAM_KEYWORDS,
    _URL_PATTERN,
    _recent_messages,
    check_message,
    is_exempt,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_message(
    content: str = "",
    author_id: int = 9999,
    author_bot: bool = False,
    guild: bool = True,
    mentions: int = 0,
    role_mentions: int = 0,
    mention_everyone: bool = False,
    roles: list[int] | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.author.id = author_id
    msg.author.bot = author_bot
    msg.guild = MagicMock() if guild else None

    # Mentions
    msg.mentions = [MagicMock() for _ in range(mentions)]
    msg.role_mentions = [MagicMock() for _ in range(role_mentions)]
    msg.mention_everyone = mention_everyone

    # Channel
    msg.channel.id = 12345
    msg.channel.name = "test-channel"

    # Author roles (for exempt check)
    if roles:
        msg.author.roles = [MagicMock(id=rid) for rid in roles]
        # Make isinstance check work for discord.Member
        msg.author.__class__ = type("Member", (), {})
    else:
        msg.author.roles = []

    # Delete method
    msg.delete = AsyncMock()

    return msg


class TestSpamKeywords:
    """Test the _SPAM_KEYWORDS regex against known spam patterns."""

    @pytest.mark.parametrize("text", [
        "免费开放的VIP群组",
        "名額有限，立即加入",
        "點擊連結加入我們",
        "全程指导稳赚不赔",
        "私信领取免费信号",
        "加微信 abc123",
        "加vx了解详情",
        "免费带单，保本保息",
        "日赚500不是梦",
        "月入10000很简单",
        "内幕消息不要错过",
        "牛股推荐每日更新",
        "股票配资低门槛",
        "杀猪盘注意防范",
        "传销拉人头",
        "色情赌博网站",
        "刷单兼职日结",
        "贷款信用卡套现",
        "Guaranteed profit with zero risk!",
        "Double your money in 24 hours",
        "Check my bio for free signals",
        "Free crypto airdrop claim now!",
        "Make $500 per day from home",
        "Join my WhatsApp group for signals",
    ])
    def test_matches_spam(self, text: str) -> None:
        assert _SPAM_KEYWORDS.search(text), f"Should match spam: {text}"

    @pytest.mark.parametrize("text", [
        "今天大盘走势如何？",
        "我觉得这只股票有潜力",
        "感谢分享",
        "老师好，请问黄金怎么看？",
        "明天是否会反弹？",
        "I think the market will go up",
        "Great analysis, thanks!",
        "What's your target for AAPL?",
    ])
    def test_no_match_clean(self, text: str) -> None:
        assert _SPAM_KEYWORDS.search(text) is None, f"Should not match clean: {text}"


class TestExternalLinks:
    """Test external platform link detection."""

    @pytest.mark.parametrize("text", [
        "Join us at t.me/spamgroup",
        "Contact via wa.me/123456",
        "Click bit.ly/abc for details",
        "See telegram.me/channel",
    ])
    def test_matches_external(self, text: str) -> None:
        assert _EXTERNAL_PLATFORM_LINKS.search(text)

    def test_no_match_normal_url(self) -> None:
        assert _EXTERNAL_PLATFORM_LINKS.search("https://github.com/repo") is None


class TestDiscordInvite:
    """Test Discord invite detection."""

    @pytest.mark.parametrize("text", [
        "Join discord.gg/abcdef",
        "https://discord.com/invite/xyz123",
        "https://discordapp.com/invite/hello",
    ])
    def test_matches_invite(self, text: str) -> None:
        assert _DISCORD_INVITE.search(text)

    def test_no_match_normal(self) -> None:
        assert _DISCORD_INVITE.search("discord is great") is None


class TestCheckMessage:
    """Test the full check_message() function."""

    def setup_method(self) -> None:
        _recent_messages.clear()

    def test_clean_message(self) -> None:
        msg = _make_message("今天行情不错")
        assert check_message(msg) is None

    def test_spam_keyword(self) -> None:
        msg = _make_message("免费开放VIP群组名额有限")
        result = check_message(msg)
        assert result is not None
        assert "spam keyword" in result

    def test_external_link(self) -> None:
        msg = _make_message("加我 t.me/scamgroup")
        result = check_message(msg)
        assert result is not None
        assert "external platform link" in result

    def test_discord_invite(self) -> None:
        msg = _make_message("来我服务器 discord.gg/abc123")
        result = check_message(msg)
        assert result is not None
        assert "discord invite" in result

    def test_excessive_mentions(self) -> None:
        msg = _make_message("Everyone look!", mentions=10)
        result = check_message(msg)
        assert result is not None
        assert "excessive mentions" in result

    def test_few_mentions_ok(self) -> None:
        msg = _make_message("Hey @user1 @user2", mentions=2)
        assert check_message(msg) is None

    def test_link_flooding(self) -> None:
        urls = " ".join(f"https://spam{i}.com" for i in range(7))
        msg = _make_message(urls)
        result = check_message(msg)
        assert result is not None
        assert "link flooding" in result

    def test_few_links_ok(self) -> None:
        msg = _make_message("See https://a.com and https://b.com")
        assert check_message(msg) is None

    @patch("bot.auto_mod.AUTO_MOD_DUP_THRESHOLD", 3)
    @patch("bot.auto_mod.AUTO_MOD_DUP_WINDOW", 60)
    def test_duplicate_spam(self) -> None:
        _recent_messages.clear()
        msg1 = _make_message("buy now!!!", author_id=1001)
        assert check_message(msg1) is None
        msg2 = _make_message("buy now!!!", author_id=1001)
        assert check_message(msg2) is None
        msg3 = _make_message("buy now!!!", author_id=1001)
        result = check_message(msg3)
        assert result is not None
        assert "duplicate spam" in result

    def test_duplicate_different_users_ok(self) -> None:
        _recent_messages.clear()
        for uid in [2001, 2002, 2003]:
            msg = _make_message("same message", author_id=uid)
            assert check_message(msg) is None

    def test_empty_content(self) -> None:
        msg = _make_message("")
        assert check_message(msg) is None


class TestIsExempt:
    """Test the is_exempt() function."""

    @patch("bot.auto_mod.OWNER_USER_ID", 1000)
    def test_owner_exempt(self) -> None:
        msg = _make_message(author_id=1000)
        assert is_exempt(msg) is True

    def test_bot_exempt(self) -> None:
        msg = _make_message(author_bot=True)
        assert is_exempt(msg) is True

    def test_normal_user_not_exempt(self) -> None:
        msg = _make_message(author_id=5555)
        assert is_exempt(msg) is False

    @patch("bot.auto_mod.AUTO_MOD_EXEMPT_ROLE_IDS", [111, 222])
    def test_exempt_role(self) -> None:
        msg = _make_message(author_id=5555, roles=[111])
        # Need to patch isinstance check
        import discord as _discord
        msg.author.__class__ = _discord.Member
        assert is_exempt(msg) is True


class TestAutoModCog:
    """Test the AutoModCog on_message handler."""

    @pytest.mark.asyncio
    @patch("bot.auto_mod.AUTO_MOD_ENABLED", True)
    async def test_deletes_spam(self) -> None:
        _recent_messages.clear()
        bot = MagicMock()
        cog = AutoModCog(bot)

        msg = _make_message("免费开放VIP群组", author_id=9999)
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("bot.auto_mod.AUTO_MOD_ENABLED", False)
    async def test_disabled_no_delete(self) -> None:
        _recent_messages.clear()
        bot = MagicMock()
        cog = AutoModCog(bot)

        msg = _make_message("免费开放VIP群组", author_id=9999)
        await cog.on_message(msg)
        msg.delete.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("bot.auto_mod.AUTO_MOD_ENABLED", True)
    @patch("bot.auto_mod.OWNER_USER_ID", 1000)
    async def test_owner_exempt_no_delete(self) -> None:
        _recent_messages.clear()
        bot = MagicMock()
        cog = AutoModCog(bot)

        msg = _make_message("免费开放VIP群组", author_id=1000)
        await cog.on_message(msg)
        msg.delete.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("bot.auto_mod.AUTO_MOD_ENABLED", True)
    async def test_clean_message_no_delete(self) -> None:
        _recent_messages.clear()
        bot = MagicMock()
        cog = AutoModCog(bot)

        msg = _make_message("今天行情不错", author_id=9999)
        await cog.on_message(msg)
        msg.delete.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("bot.auto_mod.AUTO_MOD_ENABLED", True)
    async def test_dm_skipped(self) -> None:
        _recent_messages.clear()
        bot = MagicMock()
        cog = AutoModCog(bot)

        msg = _make_message("免费开放VIP群组", author_id=9999, guild=False)
        await cog.on_message(msg)
        msg.delete.assert_not_awaited()


class TestLogAction:
    """Test _log_action DMs owner and sends to log channel."""

    @pytest.mark.asyncio
    @patch("bot.auto_mod.AUTO_MOD_ENABLED", True)
    @patch("bot.auto_mod.OWNER_USER_ID", 7777)
    @patch("bot.auto_mod.AUTO_MOD_LOG_CHANNEL_ID", 0)
    async def test_dm_owner_on_delete(self) -> None:
        _recent_messages.clear()
        bot = MagicMock()
        owner_user = AsyncMock()
        bot.get_user.return_value = owner_user
        cog = AutoModCog(bot)

        msg = _make_message("免费开放VIP群组", author_id=9999)
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()
        owner_user.send.assert_awaited_once()
        # Check embed contains author id
        embed = owner_user.send.call_args[1].get("embed") or owner_user.send.call_args[0][0]
        assert isinstance(embed, discord.Embed)

    @pytest.mark.asyncio
    @patch("bot.auto_mod.OWNER_USER_ID", 0)
    async def test_dm_owner_skipped_no_owner_id(self) -> None:
        bot = MagicMock()
        cog = AutoModCog(bot)
        embed = discord.Embed(title="test")
        await cog._dm_owner(embed)
        bot.get_user.assert_not_called()

    @pytest.mark.asyncio
    @patch("bot.auto_mod.OWNER_USER_ID", 7777)
    async def test_dm_owner_forbidden_handled(self) -> None:
        bot = MagicMock()
        owner_user = AsyncMock()
        owner_user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))
        bot.get_user.return_value = owner_user
        cog = AutoModCog(bot)
        embed = discord.Embed(title="test")
        # Should not raise
        await cog._dm_owner(embed)

    @pytest.mark.asyncio
    @patch("bot.auto_mod.AUTO_MOD_ENABLED", True)
    @patch("bot.auto_mod.OWNER_USER_ID", 7777)
    @patch("bot.auto_mod.AUTO_MOD_LOG_CHANNEL_ID", 12345)
    async def test_log_channel_and_dm_both(self) -> None:
        _recent_messages.clear()
        bot = MagicMock()
        log_ch = AsyncMock(spec=discord.TextChannel)
        bot.get_channel.return_value = log_ch
        owner_user = AsyncMock()
        bot.get_user.return_value = owner_user
        cog = AutoModCog(bot)

        msg = _make_message("免费开放VIP群组", author_id=9999)
        await cog.on_message(msg)
        msg.delete.assert_awaited_once()
        log_ch.send.assert_awaited_once()
        owner_user.send.assert_awaited_once()


class TestAutoModConfig:
    """Test config defaults."""

    def test_defaults(self) -> None:
        from bot.config import (
            AUTO_MOD_DUP_THRESHOLD,
            AUTO_MOD_DUP_WINDOW,
            AUTO_MOD_MAX_LINKS,
            AUTO_MOD_MAX_MENTIONS,
        )
        assert AUTO_MOD_MAX_MENTIONS == 8
        assert AUTO_MOD_MAX_LINKS == 5
        assert AUTO_MOD_DUP_WINDOW == 60
        assert AUTO_MOD_DUP_THRESHOLD == 3
