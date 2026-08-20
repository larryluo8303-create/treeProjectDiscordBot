"""Tests for opt-in promo DMs (allowlisted notify roles only)."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


def _member(*, user_id: int, bot: bool = False, send=None) -> MagicMock:
    m = MagicMock(spec=discord.Member)
    m.id = user_id
    m.bot = bot
    m.send = send if send is not None else AsyncMock()
    return m


def _role(*, role_id: int, members: list) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.members = members
    role.mention = f"<@&{role_id}>"
    return role


def _guild(*, guild_id: int = 1) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.chunked = True
    return guild


class TestAllowlist:
    def test_rejects_ops_tag_not_in_allowlist(self):
        with patch("bot.role_dm.PROMO_NOTIFY_ROLE_IDS", [111]):
            from bot.role_dm import is_allowed_notify_role

            assert is_allowed_notify_role(111) is True
            assert is_allowed_notify_role(222) is False
            assert is_allowed_notify_role(0) is False

    def test_notify_role_error_for_non_allowlisted(self):
        with patch("bot.role_dm.PROMO_NOTIFY_ROLE_IDS", [111]):
            from bot.role_dm import notify_role_error

            role = _role(role_id=222, members=[])
            err = notify_role_error(role, required=True)
            assert err is not None
            assert "白名单" in err

    def test_empty_allowlist_error(self):
        with patch("bot.role_dm.PROMO_NOTIFY_ROLE_IDS", []):
            from bot.role_dm import notify_role_error

            err = notify_role_error(None, required=False)
            assert err is not None
            assert "PROMO_NOTIFY_ROLE_IDS" in err


class TestCollectAndLimit:
    @pytest.mark.asyncio
    async def test_filters_bots(self):
        from bot.role_dm import collect_role_members

        humans = [_member(user_id=1), _member(user_id=2)]
        bots = [_member(user_id=99, bot=True)]
        role = _role(role_id=111, members=humans + bots)
        got = await collect_role_members(_guild(), role)
        assert {m.id for m in got} == {1, 2}

    def test_over_limit_rejects(self):
        from bot.role_dm import reject_if_over_limit

        result = reject_if_over_limit(201, max_recipients=200)
        assert result is not None
        assert result["error"] == "over_limit"
        assert result["count"] == 201
        assert result["max"] == 200
        assert result["sent"] == 0

    def test_under_limit_ok(self):
        from bot.role_dm import reject_if_over_limit

        assert reject_if_over_limit(10, max_recipients=200) is None


class TestCustomIds:
    def test_parse_dm_unsub(self):
        from bot.role_dm import parse_dm_unsub_custom_id

        assert parse_dm_unsub_custom_id("promo_dm:unsub:123:456") == (123, 456)
        assert parse_dm_unsub_custom_id("promo_notify:sub:1") is None
        assert parse_dm_unsub_custom_id("promo_dm:unsub:abc:1") is None

    def test_parse_notify_toggle(self):
        from bot.role_dm import parse_notify_toggle_custom_id

        assert parse_notify_toggle_custom_id("promo_notify:sub:111") == (True, 111, None)
        assert parse_notify_toggle_custom_id("promo_notify:unsub:111") == (False, 111, None)
        assert parse_notify_toggle_custom_id("promo_notify:sub:111:222") == (True, 111, 222)
        assert parse_notify_toggle_custom_id("promo_dm:unsub:1:2") is None

    def test_welcome_notify_buttons_include_guild_id(self):
        with patch("bot.role_dm.PROMO_NOTIFY_ROLE_IDS", [111]):
            from bot.role_dm import attach_welcome_notify_buttons

            view = discord.ui.View(timeout=None)
            attach_welcome_notify_buttons(view, _guild(guild_id=222))
            ids = [c.custom_id for c in view.children]
            assert "promo_notify:sub:111:222" in ids
            assert "promo_notify:unsub:111:222" in ids
            assert {c.label for c in view.children} == {"领取通知", "取消订阅"}


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_refuses_non_allowlisted_role(self):
        with patch("bot.role_dm.PROMO_NOTIFY_ROLE_IDS", [111]):
            from bot.role_dm import broadcast_role_dm

            role = _role(role_id=999, members=[_member(user_id=1)])
            result = await broadcast_role_dm(_guild(), role, MagicMock())
            assert result["error"] == "role_not_allowed"
            assert result["sent"] == 0

    @pytest.mark.asyncio
    async def test_over_limit_does_not_send(self):
        with patch("bot.role_dm.PROMO_NOTIFY_ROLE_IDS", [111]):
            from bot.role_dm import broadcast_role_dm

            members = [_member(user_id=i) for i in range(3)]
            role = _role(role_id=111, members=members)
            result = await broadcast_role_dm(
                _guild(), role, MagicMock(), max_recipients=2, delay=0,
            )
            assert result["error"] == "over_limit"
            assert result["count"] == 3
            for m in members:
                m.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_counts_sent_and_blocked(self):
        with patch("bot.role_dm.PROMO_NOTIFY_ROLE_IDS", [111]), \
             patch("bot.role_dm.asyncio.sleep", new_callable=AsyncMock):
            from bot.role_dm import broadcast_role_dm

            ok = _member(user_id=1)
            blocked = _member(user_id=2)
            blocked.send = AsyncMock(
                side_effect=discord.Forbidden(MagicMock(status=403), "Cannot DM"),
            )
            role = _role(role_id=111, members=[ok, blocked])
            result = await broadcast_role_dm(
                _guild(), role, MagicMock(), delay=0, max_recipients=10,
            )
            assert result.get("error") is None
            assert result["sent"] == 1
            assert result["blocked"] == 1
            assert result["failed"] == 0
            ok.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_members(self):
        with patch("bot.role_dm.PROMO_NOTIFY_ROLE_IDS", [111]):
            from bot.role_dm import broadcast_role_dm

            role = _role(role_id=111, members=[_member(user_id=9, bot=True)])
            result = await broadcast_role_dm(_guild(), role, MagicMock(), delay=0)
            assert result["error"] == "no_members"


class TestAddPromoStoresDmRole:
    def test_dm_role_id_persisted(self, tmp_path):
        import bot.scheduler as sched

        orig = sched.PROMOS_FILE
        sched.PROMOS_FILE = str(tmp_path / "promos.json")
        try:
            from datetime import datetime, timezone

            promo = sched.add_promo(
                "Sale",
                "Desc",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                [1],
                99,
                dm_role_id=111,
            )
            assert promo["dm_role_id"] == 111
            listed = sched.list_promos()
            assert listed[0]["dm_role_id"] == 111
        finally:
            sched.PROMOS_FILE = orig

    def test_omitted_dm_role_not_stored(self, tmp_path):
        import bot.scheduler as sched

        orig = sched.PROMOS_FILE
        sched.PROMOS_FILE = str(tmp_path / "promos.json")
        try:
            from datetime import datetime, timezone

            promo = sched.add_promo(
                "Sale",
                "Desc",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                [1],
                99,
            )
            assert "dm_role_id" not in promo
        finally:
            sched.PROMOS_FILE = orig
