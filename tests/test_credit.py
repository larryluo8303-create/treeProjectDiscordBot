"""Tests for the bigTreeSignal credit ledger + commands.

Pure logic + unittest.mock only — no network, no real Discord calls.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import bot.credit as credit_mod
from bot.credit import (
    InsufficientCredit,
    get_balance,
    get_tv_username,
    grant,
    link_tv,
    recent_txns,
    use,
)
from bot.credit_cog import CreditCog, _parse_amount


@pytest.fixture
def credit_file(tmp_path, monkeypatch):
    """把 ledger 状态文件指向临时目录。"""
    p = tmp_path / "credits.json"
    monkeypatch.setattr(credit_mod, "CREDIT_STATE_FILE", str(p))
    return p


# ── ledger：grant / use ──────────────────────────────────────────────────

def test_grant_new_account(credit_file):
    bal = grant(111, 41.40, reason="black friday", by=999)
    assert bal == 41.40
    assert get_balance(111) == 41.40


def test_grant_accumulates(credit_file):
    grant(111, 41.40, by=999)
    bal = grant(111, 8.60, by=999)
    assert bal == 50.00
    assert get_balance(111) == 50.00


def test_grant_rounds_to_2dp(credit_file):
    bal = grant(111, 10.005, by=999)
    assert bal == 10.01  # 本机 round(10.005, 2) == 10.01（已验证确定性行为）
    assert get_balance(111) == bal


def test_grant_rejects_non_positive(credit_file):
    with pytest.raises(ValueError):
        grant(111, 0, by=999)
    with pytest.raises(ValueError):
        grant(111, -5, by=999)
    assert get_balance(111) == 0.0


def test_grant_with_tv_username(credit_file):
    grant(111, 10, by=999, tv_username="trader_joe")
    assert get_tv_username(111) == "trader_joe"


def test_use_reduces_balance(credit_file):
    grant(111, 100, by=999)
    bal = use(111, 37.80, reason="renewal", by=999)
    assert bal == 62.20
    assert get_balance(111) == 62.20


def test_use_insufficient_raises_and_keeps_balance(credit_file):
    grant(111, 50, by=999)
    with pytest.raises(InsufficientCredit) as exc_info:
        use(111, 50.01, by=999)
    assert exc_info.value.balance == 50.00
    assert exc_info.value.requested == 50.01
    assert get_balance(111) == 50.00  # 未扣款


def test_use_exact_balance_ok(credit_file):
    grant(111, 50, by=999)
    assert use(111, 50, by=999) == 0.00


def test_use_rejects_non_positive(credit_file):
    grant(111, 50, by=999)
    with pytest.raises(ValueError):
        use(111, 0, by=999)
    assert get_balance(111) == 50.00


def test_balance_unknown_user_is_zero(credit_file):
    assert get_balance(424242) == 0.0


def test_recent_txns_order_and_limit(credit_file):
    grant(111, 10, reason="a", by=999)
    grant(111, 20, reason="b", by=999)
    use(111, 5, reason="c", by=999)
    txns = recent_txns(111, 5)
    assert [t["type"] for t in txns] == ["use", "grant", "grant"]
    assert txns[0]["reason"] == "c"
    assert len(recent_txns(111, 2)) == 2
    assert recent_txns(424242) == []


def test_link_tv(credit_file):
    assert link_tv(111, "  trader_joe ") == "trader_joe"
    assert get_tv_username(111) == "trader_joe"


def test_link_tv_rejects_empty(credit_file):
    with pytest.raises(ValueError):
        link_tv(111, "   ")


def test_state_persists_across_loads(credit_file):
    grant(111, 25.50, reason="x", by=999)
    # 重新读文件（模拟进程重启）
    assert get_balance(111) == 25.50
    assert len(recent_txns(111)) == 1


# ── _parse_amount ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("10", 10.00),
    ("$41.40", 41.40),
    ("1,000.5", 1000.50),
    ("  7.777 ", 7.78),
    ("0", None),
    ("-3", None),
    ("abc", None),
    ("", None),
])
def test_parse_amount(raw, expected):
    assert _parse_amount(raw) == expected


# ── 命令权限 ─────────────────────────────────────────────────────────────

def _cog():
    return CreditCog(bot=MagicMock())


async def _run_checks(cmd, administrator: bool):
    ctx = MagicMock()
    ctx.permissions = discord.Permissions(administrator=administrator)
    for check in cmd.checks:
        result = check(ctx)
        if hasattr(result, "__await__"):
            result = await result
        assert result in (True, None)


@pytest.mark.asyncio
async def test_grant_credit_rejects_non_admin():
    cog = _cog()
    ctx = MagicMock()
    ctx.permissions = discord.Permissions(administrator=False)
    with pytest.raises(commands.MissingPermissions):
        for check in cog.grant_credit.checks:
            result = check(ctx)
            if hasattr(result, "__await__"):
                await result


@pytest.mark.asyncio
async def test_use_credit_rejects_non_admin():
    cog = _cog()
    ctx = MagicMock()
    ctx.permissions = discord.Permissions(administrator=False)
    with pytest.raises(commands.MissingPermissions):
        for check in cog.use_credit.checks:
            result = check(ctx)
            if hasattr(result, "__await__"):
                await result


@pytest.mark.asyncio
async def test_link_tv_rejects_non_admin():
    cog = _cog()
    ctx = MagicMock()
    ctx.permissions = discord.Permissions(administrator=False)
    with pytest.raises(commands.MissingPermissions):
        for check in cog.link_tv_cmd.checks:
            result = check(ctx)
            if hasattr(result, "__await__"):
                await result


@pytest.mark.asyncio
async def test_admin_checks_pass():
    cog = _cog()
    for cmd in (cog.grant_credit, cog.use_credit, cog.link_tv_cmd):
        await _run_checks(cmd, administrator=True)


# ── 命令行为 ─────────────────────────────────────────────────────────────

def _member(uid=111, dm_blocked=False):
    m = MagicMock()
    m.id = uid
    m.mention = f"<@{uid}>"
    if dm_blocked:
        m.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "blocked"))
    else:
        m.send = AsyncMock()
    return m


def _ctx(author_id=999):
    ctx = MagicMock()
    ctx.author.id = author_id
    ctx.reply = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_grant_credit_happy_path(credit_file):
    cog = _cog()
    ctx, member = _ctx(), _member()
    await cog.grant_credit.callback(cog, ctx, member, "41.40", reason="black friday")
    assert get_balance(111) == 41.40
    member.send.assert_awaited_once()
    dm_text = member.send.await_args.args[0]
    assert "$41.40" in dm_text and "black friday" in dm_text
    reply_text = ctx.reply.await_args.args[0]
    assert "$41.40" in reply_text and "<@111>" in reply_text


@pytest.mark.asyncio
async def test_grant_credit_dm_blocked_still_ok(credit_file):
    cog = _cog()
    ctx, member = _ctx(), _member(dm_blocked=True)
    await cog.grant_credit.callback(cog, ctx, member, "10")
    assert get_balance(111) == 10.00
    ctx.reply.assert_awaited_once()  # 不抛异常，照常回复


@pytest.mark.asyncio
async def test_grant_credit_bad_amount(credit_file):
    cog = _cog()
    ctx, member = _ctx(), _member()
    await cog.grant_credit.callback(cog, ctx, member, "abc")
    assert get_balance(111) == 0.0
    assert "无效" in ctx.reply.await_args.args[0]


@pytest.mark.asyncio
async def test_use_credit_happy_path(credit_file):
    cog = _cog()
    grant(111, 100, by=999)
    ctx, member = _ctx(), _member()
    await cog.use_credit.callback(cog, ctx, member, "37.8", reason="renewal")
    assert get_balance(111) == 62.20
    dm_text = member.send.await_args.args[0]
    assert "$37.80" in dm_text and "renewal" in dm_text


@pytest.mark.asyncio
async def test_use_credit_insufficient_no_deduction(credit_file):
    cog = _cog()
    grant(111, 10, by=999)
    ctx, member = _ctx(), _member()
    await cog.use_credit.callback(cog, ctx, member, "99")
    assert get_balance(111) == 10.00  # 未扣款
    assert "余额不足" in ctx.reply.await_args.args[0]
    member.send.assert_not_awaited()  # 失败不发 DM


@pytest.mark.asyncio
async def test_link_tv_cmd(credit_file):
    cog = _cog()
    ctx, member = _ctx(), _member()
    await cog.link_tv_cmd.callback(cog, ctx, member, "trader_joe")
    assert get_tv_username(111) == "trader_joe"
    assert "trader_joe" in ctx.reply.await_args.args[0]


@pytest.mark.asyncio
async def test_my_credit_ephemeral(credit_file):
    cog = _cog()
    grant(111, 41.40, reason="black friday", by=999)
    use(111, 10, reason="renewal", by=999)
    link_tv(111, "trader_joe")
    interaction = MagicMock()
    interaction.user.id = 111
    interaction.response.send_message = AsyncMock()
    await cog.my_credit.callback(cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.await_args.kwargs
    assert kwargs.get("ephemeral") is True
    text = interaction.response.send_message.await_args.args[0]
    assert "$31.40" in text
    assert "trader_joe" in text
    assert "black friday" in text and "renewal" in text
