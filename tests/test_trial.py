"""Tests for the 免费试用30天 feature.

Pure logic + unittest.mock only — no network, no real Discord calls.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import asyncio
import inspect

import discord
import pytest

import bot.trial_cog as trial_cog
from bot.trial_cog import (
    TRIAL30_DRIP,
    TRIAL30_PROMO_TEMPLATE,
    check_trial_eligibility,
    drip_gate,
    due_drips,
    is_stop_message,
    load_trial30_state,
    promo_gate,
)

UTC = timezone.utc


def _now():
    return datetime.now(UTC)


def _old_account():
    return _now() - timedelta(days=60)


# ── 资格检查 ───────────────────────────────────────────────────────────────

def test_eligibility_pass():
    ok, reason = check_trial_eligibility(
        has_paid_role=False,
        already_claimed=False,
        account_created_at=_old_account(),
        now=_now(),
    )
    assert (ok, reason) == (True, "ok")


def test_eligibility_reject_paid_role():
    ok, reason = check_trial_eligibility(
        has_paid_role=True,
        already_claimed=False,
        account_created_at=_old_account(),
        now=_now(),
    )
    assert (ok, reason) == (False, "paid")


def test_eligibility_reject_already_claimed_second_time():
    # 终身只领一次：同一 uid 第二次领被拒
    now = _now()
    first = check_trial_eligibility(
        has_paid_role=False, already_claimed=False,
        account_created_at=_old_account(), now=now,
    )
    assert first == (True, "ok")
    second = check_trial_eligibility(
        has_paid_role=False, already_claimed=True,
        account_created_at=_old_account(), now=now,
    )
    assert second == (False, "claimed")


def test_eligibility_reject_new_account():
    ok, reason = check_trial_eligibility(
        has_paid_role=False,
        already_claimed=False,
        account_created_at=_now() - timedelta(days=10),
        now=_now(),
        min_account_age_days=30,
    )
    assert (ok, reason) == (False, "account_too_new")


def test_eligibility_boundary_exactly_30_days_passes():
    ok, reason = check_trial_eligibility(
        has_paid_role=False,
        already_claimed=False,
        account_created_at=_now() - timedelta(days=30, seconds=5),
        now=_now(),
        min_account_age_days=30,
    )
    assert (ok, reason) == (True, "ok")


def test_eligibility_reject_unknown_created_at():
    ok, reason = check_trial_eligibility(
        has_paid_role=False, already_claimed=False,
        account_created_at=None, now=_now(),
    )
    assert (ok, reason) == (False, "account_too_new")


# ── drip 调度 ──────────────────────────────────────────────────────────────

def test_due_drips_basic():
    started = _now() - timedelta(days=8)
    assert due_drips(started, _now(), []) == [1, 7]


def test_due_drips_excludes_sent():
    started = _now() - timedelta(days=8)
    assert due_drips(started, _now(), [1]) == [7]


def test_due_drips_none_due_yet():
    started = _now() - timedelta(hours=12)
    assert due_drips(started, _now(), []) == []


def test_due_drips_all_days():
    started = _now() - timedelta(days=40)
    assert due_drips(started, _now(), []) == [1, 7, 14, 21, 25, 30]


def test_due_drips_naive_started_at():
    started = datetime.now() - timedelta(days=8)  # naive
    assert due_drips(started, _now(), []) == [1, 7]


# ── STOP 关键词 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("content", [
    "STOP", "stop", " Stop ", "退订", " 退订 ", "取消", "unsubscribe",
    "TD", "td", "Td",
])
def test_is_stop_message_true(content):
    assert is_stop_message(content) is True


@pytest.mark.parametrize("content", [
    "hello", "stop please", "不退订", "", "   ", "stop!", "stops",
])
def test_is_stop_message_false(content):
    assert is_stop_message(content) is False


def test_is_stop_message_none():
    assert is_stop_message(None) is False


# ── 门控：退订后不再发 ─────────────────────────────────────────────────────

def _state_with(uid, **kwargs):
    st = {"claimed": {str(uid): {
        "started_at": (_now() - timedelta(days=2)).isoformat(),
        "expires_at": (_now() + timedelta(days=28)).isoformat(),
        "role_granted": True,
        "drip_sent": [],
        "promo_dm_sent": False,
    }}, "opt_out": [], "seen_first_msg": []}
    st["claimed"][str(uid)].update(kwargs)
    return st


def test_promo_gate_opt_out_blocks():
    st = _state_with(123)
    st["opt_out"] = ["123"]
    ok, reason = promo_gate(
        123, has_paid_role=False, already_claimed=False,
        account_created_at=_old_account(), state=st, now=_now(),
    )
    assert (ok, reason) == (False, "opt_out")


def test_promo_gate_blocks_paid_and_claimed():
    st = _state_with(123)
    assert promo_gate(123, has_paid_role=True, already_claimed=False,
                      account_created_at=_old_account(), state=st,
                      now=_now()) == (False, "paid")
    assert promo_gate(123, has_paid_role=False, already_claimed=True,
                      account_created_at=_old_account(), state=st,
                      now=_now()) == (False, "claimed")


def test_promo_gate_blocks_repeat_promo():
    st = _state_with(123, promo_dm_sent=True)
    ok, reason = promo_gate(
        123, has_paid_role=False, already_claimed=False,
        account_created_at=_old_account(), state=st, now=_now(),
    )
    assert (ok, reason) == (False, "promo_sent")


def test_promo_gate_pass():
    st = _state_with(123)
    assert promo_gate(
        123, has_paid_role=False, already_claimed=False,
        account_created_at=_old_account(), state=st, now=_now(),
    ) == (True, "ok")


def test_drip_gate_opt_out_blocks():
    st = _state_with(123)
    st["opt_out"] = ["123"]
    assert drip_gate(123, 7, st) == (False, "opt_out")


def test_drip_gate_already_sent_blocks():
    st = _state_with(123, drip_sent=[7])
    assert drip_gate(123, 7, st) == (False, "already_sent")


def test_drip_gate_not_claimed_blocks():
    st = _state_with(123)
    assert drip_gate(999, 7, st) == (False, "not_claimed")


def test_drip_gate_pass():
    st = _state_with(123)
    assert drip_gate(123, 7, st) == (True, "ok")


def test_drip_copy_complete():
    assert set(TRIAL30_DRIP) == {1, 7, 14, 21, 25, 30}
    assert all(isinstance(v, str) and v.strip() for v in TRIAL30_DRIP.values())


def test_promo_template_renders():
    text = TRIAL30_PROMO_TEMPLATE.format(name="小明")
    assert "小明" in text and "免费信号体验活动" in text and "✅" in text
    assert "STOP" in text


def test_granted_confirm_renders():
    from bot.trial_cog import TRIAL30_GRANTED_CONFIRM
    assert "信号体验" in TRIAL30_GRANTED_CONFIRM
    assert "TradingView" in TRIAL30_GRANTED_CONFIRM
    assert "截图" in TRIAL30_GRANTED_CONFIRM


def test_tvdone_confirm_renders():
    from bot.trial_cog import TRIAL30_TVDONE_CONFIRM
    assert "TradingView" in TRIAL30_TVDONE_CONFIRM and "已开通" in TRIAL30_TVDONE_CONFIRM


def test_button_ids_match_broadcast_script():
    # cog 与群发脚本的 custom_id 必须一致，否则按钮点击无人处理
    from bot.trial_cog import TRIAL_JOIN_BUTTON_ID
    assert TRIAL_JOIN_BUTTON_ID == "trial_join"


# ── 活动有效期 ─────────────────────────────────────────────────────────────

def test_campaign_active_before_end():
    from bot.trial_config import campaign_active
    assert campaign_active(datetime(2026, 10, 17, tzinfo=UTC)) is True
    assert campaign_active(datetime(2026, 12, 31, 12, tzinfo=UTC)) is True


def test_campaign_active_after_end():
    from bot.trial_config import campaign_active
    assert campaign_active(datetime(2027, 1, 1, tzinfo=UTC)) is False


def test_campaign_active_bad_format_fail_open(monkeypatch):
    import bot.trial_config as cfg
    monkeypatch.setattr(cfg, "TRIAL_CAMPAIGN_END", "not-a-date")
    assert cfg.campaign_active() is True


# ── mock：!试用 领取流程 ───────────────────────────────────────────────────

def _make_member(**kwargs):
    member = MagicMock(spec=discord.Member)
    member.id = kwargs.get("id", 123)
    member.bot = False
    member.roles = kwargs.get("roles", [])
    member.created_at = kwargs.get("created_at", _old_account())
    member.display_name = "tester"
    member.send = AsyncMock()
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    return member


def _make_guild(roles=()):
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    guild.roles = list(roles)
    role = MagicMock(spec=discord.Role)
    role.name = "placeholder"
    guild.create_role = AsyncMock(return_value=role)
    return guild, role


def _enable_cog(monkeypatch, tmp_path):
    monkeypatch.setattr(trial_cog, "TRIAL30_ENABLED", True)
    monkeypatch.setattr(
        trial_cog, "TRIAL30_STATE_FILE", str(tmp_path / "trial30.json")
    )
    bot = MagicMock()
    bot.get_user = MagicMock(return_value=None)
    bot.fetch_user = AsyncMock()
    bot.get_guild = MagicMock(return_value=None)
    bot.guilds = []
    return trial_cog.TrialCog(bot), bot


def _make_guild_with_trial_role():
    trial_role = MagicMock(spec=discord.Role)
    trial_role.name = trial_cog.TRIAL30_ROLE_NAME
    guild, _ = _make_guild(roles=(trial_role,))
    return guild, trial_role


async def test_claim_command_grants_role_immediately(monkeypatch, tmp_path):
    # v3：!试用 资格通过 → 立即发放「信号体验」组并开始计时
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member()
    guild, trial_role = _make_guild_with_trial_role()
    ctx = MagicMock()
    ctx.author = member
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.claim_trial.callback(cog, ctx)

    member.add_roles.assert_awaited_once_with(
        trial_role, reason=f"trial30 grant ({trial_cog.TRIAL30_DAYS}d)"
    )
    member.send.assert_awaited_once()  # 开通确认 DM（含 TV 指引）
    confirm = member.send.await_args.args[0]
    assert "信号体验" in confirm and "TradingView" in confirm and "截图" in confirm
    reply = ctx.reply.await_args.args[0]
    assert "已为你开通" in reply
    st = load_trial30_state()
    rec = st["claimed"]["123"]
    assert rec["role_granted"] is True
    assert "started_at" in rec and "expires_at" in rec
    assert rec["tv_username"] is None and rec["tv_granted"] is False


async def test_claim_command_second_time_rejected(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member()
    guild, _ = _make_guild_with_trial_role()
    ctx = MagicMock()
    ctx.author = member
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.claim_trial.callback(cog, ctx)
    await cog.claim_trial.callback(cog, ctx)  # 第二次

    assert member.add_roles.await_count == 1  # 只发一次
    second_reply = ctx.reply.await_args.args[0]
    assert "只能参加一次" in second_reply


async def test_claim_command_dm_closed_shows_confirm_in_channel(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member()
    guild, _ = _make_guild_with_trial_role()
    forbidden = discord.Forbidden(MagicMock(), "closed")
    member.send = AsyncMock(side_effect=forbidden)
    ctx = MagicMock()
    ctx.author = member
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.claim_trial.callback(cog, ctx)

    member.add_roles.assert_awaited_once()  # 组照发
    reply = ctx.reply.await_args.args[0]
    assert "私信关着" in reply and "信号体验" in reply


async def test_claim_command_campaign_ended_refuses(monkeypatch, tmp_path):
    import bot.trial_config as cfg
    monkeypatch.setattr(cfg, "TRIAL_CAMPAIGN_END", "2020-01-01")
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member()
    guild, _ = _make_guild_with_trial_role()
    ctx = MagicMock()
    ctx.author = member
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.claim_trial.callback(cog, ctx)

    member.add_roles.assert_not_called()
    assert "已结束" in ctx.reply.await_args.args[0]
    assert load_trial30_state()["claimed"] == {}


# ── mock：✅ 报名按钮 ────────────────────────────────────────────────────

def _make_interaction(member, custom_id="trial_join"):
    inter = MagicMock(spec=discord.Interaction)
    inter.type = discord.InteractionType.component
    inter.data = {"custom_id": custom_id}
    inter.user = member
    inter.response = MagicMock()
    inter.response.defer = AsyncMock()
    inter.response.send_message = AsyncMock()
    inter.followup = MagicMock()
    inter.followup.send = AsyncMock()
    return inter


async def test_button_click_grants_trial(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member()
    guild, trial_role = _make_guild_with_trial_role()
    member.guild = guild
    bot.guilds = [guild]
    inter = _make_interaction(member)

    await cog.on_interaction(inter)

    member.add_roles.assert_awaited_once_with(
        trial_role, reason=f"trial30 grant ({trial_cog.TRIAL30_DAYS}d)"
    )
    inter.response.defer.assert_awaited_once()
    inter.followup.send.assert_awaited_once()
    assert "信号体验" in inter.followup.send.await_args.args[0]
    member.send.assert_awaited_once()  # DM 确认
    rec = load_trial30_state()["claimed"]["123"]
    assert rec["role_granted"] is True and "started_at" in rec


async def test_button_click_ignores_other_custom_id(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member()
    inter = _make_interaction(member, custom_id="something_else")

    await cog.on_interaction(inter)

    member.add_roles.assert_not_called()
    inter.response.defer.assert_not_called()
    inter.followup.send.assert_not_called()


async def test_button_click_second_time_rejected(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member()
    guild, trial_role = _make_guild_with_trial_role()
    member.guild = guild
    bot.guilds = [guild]
    inter = _make_interaction(member)
    await cog.on_interaction(inter)
    inter2 = _make_interaction(member)
    await cog.on_interaction(inter2)

    assert member.add_roles.await_count == 1
    assert "只能参加一次" in inter2.followup.send.await_args.args[0]


async def test_button_click_campaign_ended(monkeypatch, tmp_path):
    import bot.trial_config as cfg
    monkeypatch.setattr(cfg, "TRIAL_CAMPAIGN_END", "2020-01-01")
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member()
    guild, _ = _make_guild_with_trial_role()
    member.guild = guild
    bot.guilds = [guild]
    inter = _make_interaction(member)

    await cog.on_interaction(inter)

    member.add_roles.assert_not_called()
    assert "已结束" in inter.followup.send.await_args.args[0]


async def test_button_click_disabled_is_silent(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    monkeypatch.setattr(trial_cog, "TRIAL30_ENABLED", False)
    member = _make_member()
    inter = _make_interaction(member)

    await cog.on_interaction(inter)

    member.add_roles.assert_not_called()
    inter.response.send_message.assert_awaited_once()
    inter.followup.send.assert_not_called()


async def test_tvdone_records_tv_and_dms_user(monkeypatch, tmp_path):
    # v3：先报名（发组+计时），再 !tvdone 只记录 TV 用户名并 DM 确认
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member(id=777)
    guild, _ = _make_guild_with_trial_role()
    ok, _ = await cog._grant_trial(member, guild)
    assert ok is True
    ctx = MagicMock()
    ctx.author = _make_member(id=1)  # 管理员（check 走 callback 不校验）
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.tvdone.callback(cog, ctx, member, tv_username="mytvuser123")

    member.send.assert_awaited()  # 开通确认 DM
    confirm = member.send.await_args.args[0]
    assert "已开通" in confirm and "TradingView" in confirm
    admin_reply = ctx.reply.await_args.args[0]
    assert "mytvuser123" in admin_reply
    st = load_trial30_state()
    rec = st["claimed"]["777"]
    assert rec["tv_username"] == "mytvuser123"
    assert rec["tv_granted"] is True
    assert rec["role_granted"] is True
    assert "started_at" in rec and "expires_at" in rec


async def test_tvdone_second_time_reports_already_recorded(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member(id=779)
    guild, _ = _make_guild_with_trial_role()
    await cog._grant_trial(member, guild)
    ctx = MagicMock()
    ctx.author = _make_member(id=1)
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.tvdone.callback(cog, ctx, member, tv_username="tvuser779")
    await cog.tvdone.callback(cog, ctx, member, tv_username="tvuser779")  # 第二次

    assert "已标记过" in ctx.reply.await_args.args[0]
    assert load_trial30_state()["claimed"]["779"]["tv_username"] == "tvuser779"


async def test_tvdone_fallback_grants_for_missing_record(monkeypatch, tmp_path):
    # 用户没走报名流程：tvdone 兜底补发组并开始计时
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member(id=782)
    guild, _ = _make_guild_with_trial_role()
    ctx = MagicMock()
    ctx.author = _make_member(id=1)
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.tvdone.callback(cog, ctx, member, tv_username="tvuser782")

    member.add_roles.assert_awaited_once()
    rec = load_trial30_state()["claimed"]["782"]
    assert rec["role_granted"] is True and rec["tv_granted"] is True
    assert rec["tv_username"] == "tvuser782"


async def test_tvdone_requires_username(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member(id=780)
    guild, _ = _make_guild()
    ctx = MagicMock()
    ctx.author = _make_member(id=1)
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.tvdone.callback(cog, ctx, member, tv_username="   ")

    assert "用法" in ctx.reply.await_args.args[0]
    member.add_roles.assert_not_called()
    assert load_trial30_state()["claimed"] == {}


async def test_tvdone_requires_administrator():
    # has_permissions(administrator=True) 检查存在：非管理员调用抛 CheckFailure
    import discord.ext.commands as commands_mod

    cog = trial_cog.TrialCog(MagicMock())
    assert len(cog.tvdone.checks) > 0
    ctx = MagicMock()
    ctx.author.guild_permissions.administrator = False
    with pytest.raises(commands_mod.CheckFailure):
        for check in cog.tvdone.checks:
            await check(ctx)


async def test_tvdone_disabled_is_silent(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    monkeypatch.setattr(trial_cog, "TRIAL30_ENABLED", False)
    member = _make_member(id=781)
    guild, _ = _make_guild()
    ctx = MagicMock()
    ctx.author = _make_member(id=1)
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.tvdone.callback(cog, ctx, member, tv_username="tvuser781")

    ctx.reply.assert_not_called()
    member.add_roles.assert_not_called()


def test_drip_gate_not_granted_blocks():
    st = _state_with(123)
    st["claimed"]["123"]["role_granted"] = False
    assert drip_gate(123, 1, st) == (False, "not_granted")


async def test_claim_command_reject_paid(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    paid_role = MagicMock(spec=discord.Role)
    paid_role.id = 1445447888439349319  # 懒人🌴
    paid_role.name = "懒人🌴"
    member = _make_member(roles=[paid_role])
    guild, _ = _make_guild()
    ctx = MagicMock()
    ctx.author = member
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.claim_trial.callback(cog, ctx)

    ctx.reply.assert_awaited_once()
    assert "付费会员" in ctx.reply.await_args.args[0]
    member.add_roles.assert_not_called()
    assert load_trial30_state()["claimed"] == {}


async def test_claim_command_disabled_is_silent(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    monkeypatch.setattr(trial_cog, "TRIAL30_ENABLED", False)
    ctx = MagicMock()
    ctx.author = _make_member()
    ctx.guild = _make_guild()[0]
    ctx.reply = AsyncMock()

    await cog.claim_trial.callback(cog, ctx)

    ctx.reply.assert_not_called()


# ── mock：STOP 退订 ────────────────────────────────────────────────────────

async def test_stop_message_records_opt_out_and_syncs_broadcast(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    broadcast_file = tmp_path / "dm_broadcast_state.json"
    monkeypatch.setattr(
        trial_cog, "BROADCAST_STATE_FILE", str(broadcast_file)
    )
    author = MagicMock(spec=discord.User)
    author.id = 456
    author.bot = False
    author.send = AsyncMock()
    message = MagicMock(spec=discord.Message)
    message.guild = None
    message.author = author
    message.content = "  STOP "

    await cog.on_message(message)

    st = load_trial30_state()
    assert "456" in st["opt_out"]
    author.send.assert_awaited_once_with("已退订，不再打扰 🙏")
    import json
    data = json.loads(broadcast_file.read_text(encoding="utf-8"))
    assert "456" in data["opted_out"]
    assert data["users"]["456"]["status"] == "opted_out"


async def test_stop_works_when_feature_disabled(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    monkeypatch.setattr(trial_cog, "TRIAL30_ENABLED", False)
    monkeypatch.setattr(
        trial_cog, "BROADCAST_STATE_FILE", str(tmp_path / "dm_broadcast_state.json")
    )
    author = MagicMock(spec=discord.User)
    author.id = 789
    author.bot = False
    author.send = AsyncMock()
    message = MagicMock(spec=discord.Message)
    message.guild = None
    message.author = author
    message.content = "退订"

    await cog.on_message(message)

    assert "789" in load_trial30_state()["opt_out"]


async def test_guild_message_first_time_triggers_promo(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    user = MagicMock(spec=discord.User)
    user.id = 321
    user.send = AsyncMock()
    bot.fetch_user = AsyncMock(return_value=user)
    member = _make_member(id=321)
    guild, _ = _make_guild()
    message = MagicMock(spec=discord.Message)
    message.guild = guild
    message.author = member
    message.content = "大家好"

    await cog.on_message(message)

    user.send.assert_awaited_once()
    assert "Hi tester" in user.send.await_args.args[0]
    st = load_trial30_state()
    assert st["claimed"]["321"]["promo_dm_sent"] is True
    assert "321" in st["seen_first_msg"]


async def test_guild_message_second_time_no_promo(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    user = MagicMock(spec=discord.User)
    user.id = 322
    user.send = AsyncMock()
    bot.fetch_user = AsyncMock(return_value=user)
    member = _make_member(id=322)
    guild, _ = _make_guild()
    message = MagicMock(spec=discord.Message)
    message.guild = guild
    message.author = member
    message.content = "大家好"

    await cog.on_message(message)
    await cog.on_message(message)  # 第二条群消息

    assert user.send.await_count == 1


# ── mock：到期回收 ────────────────────────────────────────────────────────

async def test_expiry_revokes_grants_marker_and_dms(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    trial_role = MagicMock(spec=discord.Role)
    trial_role.name = trial_cog.TRIAL30_ROLE_NAME
    expired_role = MagicMock(spec=discord.Role)
    expired_role.name = "体验过期"
    member = _make_member(id=555, roles=[trial_role])
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    guild.roles = [trial_role, expired_role]
    guild.create_role = AsyncMock()
    guild.get_member = MagicMock(return_value=member)
    bot.get_guild = MagicMock(return_value=guild)
    bot.guilds = [guild]
    dm_user = MagicMock(spec=discord.User)
    dm_user.send = AsyncMock()
    bot.fetch_user = AsyncMock(return_value=dm_user)

    st = load_trial30_state()
    st["claimed"]["555"] = {
        "started_at": (_now() - timedelta(days=31)).isoformat(),
        "expires_at": (_now() - timedelta(days=1)).isoformat(),
        "drip_sent": [1, 7, 14, 21, 25],
        "promo_dm_sent": False,
        "guild_id": 999,
    }
    trial_cog.save_trial30_state(st)

    await cog._process_expiries()

    member.remove_roles.assert_awaited_once_with(trial_role, reason="trial30 expired")
    member.add_roles.assert_awaited_once()
    assert "已到期" in dm_user.send.await_args.args[0]
    rec = load_trial30_state()["claimed"]["555"]
    assert rec["expired_done"] is True and 30 in rec["drip_sent"]


async def test_expiry_skips_opted_out_dm_but_still_revokes(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    trial_role = MagicMock(spec=discord.Role)
    trial_role.name = trial_cog.TRIAL30_ROLE_NAME
    member = _make_member(id=556, roles=[trial_role])
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    guild.roles = [trial_role]
    guild.create_role = AsyncMock()
    guild.get_member = MagicMock(return_value=member)
    bot.get_guild = MagicMock(return_value=guild)
    bot.guilds = [guild]
    bot.fetch_user = AsyncMock()

    st = load_trial30_state()
    st["opt_out"] = ["556"]
    st["claimed"]["556"] = {
        "started_at": (_now() - timedelta(days=31)).isoformat(),
        "expires_at": (_now() - timedelta(days=1)).isoformat(),
        "drip_sent": [],
        "promo_dm_sent": False,
        "guild_id": 999,
    }
    trial_cog.save_trial30_state(st)

    await cog._process_expiries()

    member.remove_roles.assert_awaited_once()
    bot.fetch_user.assert_not_called()  # 退订用户不发到期 DM
    assert load_trial30_state()["claimed"]["556"]["expired_done"] is True


# ── 回归测试：并发/幂等与 tvdone 修复 ────────────────────────────────────

async def test_concurrent_grants_grant_only_once(monkeypatch, tmp_path):
    # 快速连点 ✅：两个并发 _grant_trial 只有一个真正发组，
    # 另一个排队后看到已发放记录返回 claimed；started_at 不被重置。
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member()
    guild, trial_role = _make_guild_with_trial_role()

    results = await asyncio.gather(
        cog._grant_trial(member, guild, via="button"),
        cog._grant_trial(member, guild, via="button"),
    )
    assert results.count((True, "ok")) == 1
    assert results.count((False, "claimed")) == 1
    assert member.add_roles.await_count == 1
    rec = load_trial30_state()["claimed"]["123"]
    assert rec["role_granted"] is True
    assert rec["granted_via"] == "button"


async def test_concurrent_grant_and_promo_no_lost_update(monkeypatch, tmp_path):
    # 发放与 promo 写入并发：后落盘的一方重读合并，不丢对方的字段。
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    user = MagicMock(spec=discord.User)
    user.send = AsyncMock()
    bot.fetch_user = AsyncMock(return_value=user)
    member = _make_member(id=910)
    guild, _ = _make_guild_with_trial_role()

    await asyncio.gather(
        cog._grant_trial(member, guild, via="command"),
        cog._maybe_send_promo(member, source="reaction"),
    )
    rec = load_trial30_state()["claimed"]["910"]
    assert rec["role_granted"] is True
    assert rec["promo_dm_sent"] is True


def test_tvdone_username_is_keyword_only():
    # TV 用户名含空格不被截断：keyword-only 参数让解析器整行捕获。
    sig = inspect.signature(trial_cog.TrialCog.tvdone.callback)
    param = sig.parameters["tv_username"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


async def test_tvdone_username_with_spaces_kept_verbatim(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member(id=783)
    guild, _ = _make_guild_with_trial_role()
    await cog._grant_trial(member, guild)
    ctx = MagicMock()
    ctx.author = _make_member(id=1)
    ctx.guild = guild
    ctx.reply = AsyncMock()

    await cog.tvdone.callback(cog, ctx, member, tv_username="John Doe")

    rec = load_trial30_state()["claimed"]["783"]
    assert rec["tv_username"] == "John Doe"  # 不再是截断后的 "John"
    assert rec["tv_granted"] is True


async def test_tvdone_member_not_found_replies_clearly(monkeypatch, tmp_path):
    # @成员 解析失败（输错/已退群）：之前被静默吞掉，现在给清晰提示。
    import discord.ext.commands as commands_mod

    cog, bot = _enable_cog(monkeypatch, tmp_path)
    ctx = MagicMock()
    ctx.reply = AsyncMock()

    await cog.tvdone_error(ctx, commands_mod.MemberNotFound("nope"))

    ctx.reply.assert_awaited_once()
    reply = ctx.reply.await_args.args[0]
    assert "找不到该成员" in reply and "!tvdone" in reply


async def test_tvdone_check_failure_replies_clearly(monkeypatch, tmp_path):
    import discord.ext.commands as commands_mod

    cog, bot = _enable_cog(monkeypatch, tmp_path)
    ctx = MagicMock()
    ctx.reply = AsyncMock()

    await cog.tvdone_error(ctx, commands_mod.CheckFailure("no perm"))

    ctx.reply.assert_awaited_once()
    assert "管理员权限" in ctx.reply.await_args.args[0]


async def test_grant_records_via_source(monkeypatch, tmp_path):
    cog, bot = _enable_cog(monkeypatch, tmp_path)
    member = _make_member(id=911)
    guild, _ = _make_guild_with_trial_role()

    ok, _ = await cog._grant_trial(member, guild, via="command")

    assert ok is True
    assert load_trial30_state()["claimed"]["911"]["granted_via"] == "command"
