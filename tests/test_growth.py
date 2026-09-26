"""Tests for the growth trio: invite leaderboard/rewards, timed roles, onboarding drip."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


def _role(role_id: int, name: str):
    r = MagicMock()
    r.id = role_id
    r.name = name
    return r


def _member(user_id: int, roles=()):
    m = MagicMock()
    m.id = user_id
    m.roles = list(roles)
    m.add_roles = AsyncMock()
    m.remove_roles = AsyncMock()
    return m


def _guild_with(guild_id: int, member, role):
    guild = MagicMock()
    guild.id = guild_id
    guild.get_member.return_value = member
    guild.get_role.return_value = role
    return guild


def _bot_with(guild):
    bot = MagicMock()
    bot.get_guild.return_value = guild
    bot.get_user.return_value = None
    return bot


def _write_grants(path, grants):
    path.write_text(json.dumps(grants), encoding="utf-8")


def _expired_grant(user_id=42, guild_id=999, role_id=555, reason="trial"):
    now = datetime.now(timezone.utc)
    return {
        "user_id": user_id,
        "guild_id": guild_id,
        "role_id": role_id,
        "reason": reason,
        "days": 15,
        "granted_at": (now - timedelta(days=20)).isoformat(),
        "expires_at": (now - timedelta(days=5)).isoformat(),
        "revoked": False,
    }


class TestMonthlyTopInviters:
    def _write_invites(self, path, attributions):
        data = {"codes": {}, "counts": {}, "attributions": attributions}
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_filters_to_trailing_30_days(self, tmp_path):
        invites_file = tmp_path / "invites.json"
        now = datetime.now(timezone.utc)
        self._write_invites(invites_file, [
            {"code": "a", "inviter_id": 1, "joiner_id": 11, "guild_id": 9,
             "ts": (now - timedelta(days=40)).isoformat()},
            {"code": "a", "inviter_id": 1, "joiner_id": 12, "guild_id": 9,
             "ts": (now - timedelta(days=35)).isoformat()},
            {"code": "b", "inviter_id": 2, "joiner_id": 13, "guild_id": 9,
             "ts": (now - timedelta(days=5)).isoformat()},
        ])
        with patch("bot.acquisition.INVITES_FILE", str(invites_file)):
            from bot.acquisition import monthly_top_inviters
            assert monthly_top_inviters(3) == [(2, 1)]

    def test_rank_order_and_limit(self, tmp_path):
        invites_file = tmp_path / "invites.json"
        now = datetime.now(timezone.utc)
        attrs = []
        for uid, n in ((1, 5), (2, 3), (3, 8)):
            for j in range(n):
                attrs.append({"code": "x", "inviter_id": uid, "joiner_id": 100 + j,
                              "guild_id": 9, "ts": now.isoformat()})
        self._write_invites(invites_file, attrs)
        with patch("bot.acquisition.INVITES_FILE", str(invites_file)):
            from bot.acquisition import invite_rank_for, monthly_top_inviters
            assert monthly_top_inviters(2) == [(3, 8), (1, 5)]
            assert invite_rank_for(1) == (2, 5)
            assert invite_rank_for(999) == (0, 0)

    def test_empty(self, tmp_path):
        invites_file = tmp_path / "invites.json"
        self._write_invites(invites_file, [])
        with patch("bot.acquisition.INVITES_FILE", str(invites_file)):
            from bot.acquisition import monthly_top_inviters
            assert monthly_top_inviters(3) == []


class TestIsPaidMember:
    def test_cohort_names_are_paid(self):
        from bot.timed_roles import is_paid_member
        assert is_paid_member(_member(1, [_role(1, "懒人🌴22")])) is True
        assert is_paid_member(_member(1, [_role(1, "懒人etf25🌲")])) is True
        assert is_paid_member(_member(1, [_role(1, "懒人26Q1")])) is True

    def test_reward_and_plain_roles_not_paid(self):
        from bot.timed_roles import is_paid_member
        assert is_paid_member(_member(1, [_role(1, "懒人etf🌲")])) is False
        assert is_paid_member(_member(1, [_role(1, "懒人🌴")])) is False
        assert is_paid_member(_member(1, [_role(1, "新人体验15天")])) is False
        assert is_paid_member(_member(1, [])) is False


class TestTimedRoles:
    async def test_grant_records_and_active(self, tmp_path):
        grants_file = tmp_path / "timed.json"
        role = _role(555, "懒人etf🌲")
        member = _member(42)
        bot = _bot_with(_guild_with(999, member, role))
        with patch("bot.timed_roles.TIMED_ROLES_FILE", str(grants_file)):
            from bot.timed_roles import grant_timed_role, has_active_grant
            assert await grant_timed_role(bot, 42, 999, 555, 30, "invite_etf") is True
            member.add_roles.assert_awaited_once()
            g = has_active_grant(42, 555)
            assert g is not None
            assert g["reason"] == "invite_etf"
            exp = datetime.fromisoformat(g["expires_at"])
            assert exp > datetime.now(timezone.utc)

    async def test_grant_forbidden_degrades(self, tmp_path):
        grants_file = tmp_path / "timed.json"
        role = _role(555, "懒人etf🌲")
        member = _member(42)
        member.add_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perm"))
        bot = _bot_with(_guild_with(999, member, role))
        with patch("bot.timed_roles.TIMED_ROLES_FILE", str(grants_file)):
            from bot.timed_roles import grant_timed_role, has_active_grant
            assert await grant_timed_role(bot, 42, 999, 555, 30, "invite_etf") is False
            assert has_active_grant(42, 555) is None

    async def test_revoke_due_removes_expired(self, tmp_path):
        grants_file = tmp_path / "timed.json"
        _write_grants(grants_file, [_expired_grant()])
        role = _role(555, "新人体验15天")
        member = _member(42, [role])
        bot = _bot_with(_guild_with(999, member, role))
        with patch("bot.timed_roles.TIMED_ROLES_FILE", str(grants_file)):
            from bot.timed_roles import has_active_grant, revoke_due_timed_roles
            closed = await revoke_due_timed_roles(bot)
            assert closed == 1
            member.remove_roles.assert_awaited_once()
            assert has_active_grant(42, 555) is None

    async def test_revoke_skips_paid_member(self, tmp_path):
        grants_file = tmp_path / "timed.json"
        _write_grants(grants_file, [_expired_grant(reason="invite_etf")])
        role = _role(555, "懒人etf🌲")
        paid = _role(777, "懒人🌴22")
        member = _member(42, [role, paid])
        bot = _bot_with(_guild_with(999, member, role))
        with patch("bot.timed_roles.TIMED_ROLES_FILE", str(grants_file)):
            from bot.timed_roles import revoke_due_timed_roles
            closed = await revoke_due_timed_roles(bot)
            assert closed == 0
            member.remove_roles.assert_not_awaited()
            data = json.loads(grants_file.read_text(encoding="utf-8"))
            assert data[0].get("skipped_paid") is True

    async def test_revoke_skips_unexpired(self, tmp_path):
        grants_file = tmp_path / "timed.json"
        now = datetime.now(timezone.utc)
        g = _expired_grant()
        g["expires_at"] = (now + timedelta(days=3)).isoformat()
        _write_grants(grants_file, [g])
        role = _role(555, "新人体验15天")
        member = _member(42, [role])
        bot = _bot_with(_guild_with(999, member, role))
        with patch("bot.timed_roles.TIMED_ROLES_FILE", str(grants_file)):
            from bot.timed_roles import revoke_due_timed_roles
            assert await revoke_due_timed_roles(bot) == 0
            member.remove_roles.assert_not_awaited()

    def test_cancel_grants_for_user(self, tmp_path):
        grants_file = tmp_path / "timed.json"
        _write_grants(grants_file, [_expired_grant(user_id=42), _expired_grant(user_id=43)])
        with patch("bot.timed_roles.TIMED_ROLES_FILE", str(grants_file)):
            from bot.timed_roles import cancel_grants_for_user, has_active_grant
            assert cancel_grants_for_user(42) == 1
            data = json.loads(grants_file.read_text(encoding="utf-8"))
            assert sum(1 for g in data if g.get("cancelled")) == 1
            assert has_active_grant(43, 555) is None  # already expired anyway


class TestOnboardDripSteps:
    def test_two_steps_trial_signal_then_cta(self, tmp_path):
        drip_file = tmp_path / "drip.json"
        with patch("bot.acquisition.DRIP_FILE", str(drip_file)), \
             patch("bot.acquisition.ONBOARD_DAY1_DELAY_SECONDS", 10), \
             patch("bot.acquisition.ONBOARD_DAY3_DELAY_SECONDS", 20):
            from bot.acquisition import schedule_welcome_drip
            jobs = schedule_welcome_drip(7, 8)
            assert [j["step"] for j in jobs] == ["trial_signal", "cta"]

    def test_zero_delay_skips_step(self, tmp_path):
        drip_file = tmp_path / "drip.json"
        with patch("bot.acquisition.DRIP_FILE", str(drip_file)), \
             patch("bot.acquisition.ONBOARD_DAY1_DELAY_SECONDS", 0), \
             patch("bot.acquisition.ONBOARD_DAY3_DELAY_SECONDS", 20):
            from bot.acquisition import schedule_welcome_drip
            jobs = schedule_welcome_drip(7, 8)
            assert [j["step"] for j in jobs] == ["cta"]


class TestInviteEtfReward:
    async def test_first_invite_grants_etf_role(self, tmp_path):
        grants_file = tmp_path / "timed.json"
        role = _role(111, "懒人etf🌲")
        guild = _guild_with(999, _member(42), role)
        bot = _bot_with(guild)
        bot.fetch_user = AsyncMock(return_value=None)
        from bot.acquisition_cog import AcquisitionCog
        cog = AcquisitionCog(bot)
        with patch("bot.timed_roles.TIMED_ROLES_FILE", str(grants_file)), \
             patch("bot.acquisition_cog.INVITE_ETF_REWARD_ROLE_ID", 111), \
             patch("bot.acquisition_cog.INVITE_REWARD_DAYS", 30):
            await cog._maybe_grant_invite_etf_reward(guild, 42, 1)
            from bot.timed_roles import has_active_grant
            assert has_active_grant(42, 111) is not None
            # second invite while grant active → no duplicate grant
            await cog._maybe_grant_invite_etf_reward(guild, 42, 2)
            data = json.loads(grants_file.read_text(encoding="utf-8"))
            assert len(data) == 1

    async def test_regrant_only_after_30d_cooldown(self, tmp_path):
        grants_file = tmp_path / "timed.json"
        now = datetime.now(timezone.utc)
        old = _expired_grant(user_id=42, role_id=111, reason="invite_etf")
        old["expires_at"] = (now - timedelta(days=10)).isoformat()  # expired 10d ago
        _write_grants(grants_file, [old])
        role = _role(111, "懒人etf🌲")
        guild = _guild_with(999, _member(42), role)
        bot = _bot_with(guild)
        from bot.acquisition_cog import AcquisitionCog
        cog = AcquisitionCog(bot)
        with patch("bot.timed_roles.TIMED_ROLES_FILE", str(grants_file)), \
             patch("bot.acquisition_cog.INVITE_ETF_REWARD_ROLE_ID", 111), \
             patch("bot.acquisition_cog.INVITE_REWARD_DAYS", 30):
            await cog._maybe_grant_invite_etf_reward(guild, 42, 1)
            data = json.loads(grants_file.read_text(encoding="utf-8"))
            assert len(data) == 1  # still in 30d cooldown → no new grant
            # expire it 40 days ago → re-grant allowed
            old["expires_at"] = (now - timedelta(days=40)).isoformat()
            _write_grants(grants_file, [old])
            await cog._maybe_grant_invite_etf_reward(guild, 42, 2)
            data = json.loads(grants_file.read_text(encoding="utf-8"))
            assert len(data) == 2
