"""Tests for the bigTreeSignal credit ledger + commands (TV-主键版)。

主键是 TradingView 用户名（大小写不敏感）；Discord ID 只用于反查。
Pure logic + unittest.mock only — no network, no real Discord calls.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import bot.credit as credit_mod
from bot.credit import (
    InsufficientCredit,
    get_account_info,
    get_balance,
    get_tv_username,
    grant,
    link_tv,
    recent_txns,
    relink_discord,
    resolve_by_discord,
    use,
)
from bot.credit_cog import CreditCog, _parse_amount


@pytest.fixture
def credit_file(tmp_path, monkeypatch):
    """把 ledger 状态文件指向临时目录。"""
    p = tmp_path / "credits.json"
    monkeypatch.setattr(credit_mod, "CREDIT_STATE_FILE", str(p))
    return p


# ── ledger：grant / use（TV 主键） ─────────────────────────────────────────

def test_grant_new_tv_account(credit_file):
    bal = grant("Trader_Joe", 41.40, reason="black friday", by=999)
    assert bal == 41.40
    assert get_balance("trader_joe") == 41.40
    info = get_account_info("TRADER_JOE")
    assert info["tv_username"] == "Trader_Joe"  # 原始大小写保留
    assert info["balance"] == 41.40


def test_grant_case_insensitive_same_account(credit_file):
    grant("trader_joe", 41.40, by=999)
    bal = grant("TRADER_JOE", 8.60, by=999)
    assert bal == 50.00
    assert get_balance("Trader_Joe") == 50.00


def test_grant_rounds_to_2dp(credit_file):
    bal = grant("trader_joe", 10.005, by=999)
    assert bal == 10.01
    assert get_balance("trader_joe") == bal


def test_grant_rejects_non_positive(credit_file):
    with pytest.raises(ValueError):
        grant("trader_joe", 0, by=999)
    with pytest.raises(ValueError):
        grant("trader_joe", -5, by=999)
    assert get_balance("trader_joe") == 0.0


def test_grant_rejects_empty_tv_and_no_discord(credit_file):
    with pytest.raises(ValueError):
        grant("", 10, by=999)
    with pytest.raises(ValueError):
        grant(None, 10, by=999)


def test_grant_with_discord_id_builds_index(credit_file):
    grant("trader_joe", 10, by=999, discord_id=111)
    assert resolve_by_discord(111) == "trader_joe"
    assert get_tv_username(111) == "trader_joe"


def test_grant_discord_fallback_no_tv(credit_file):
    bal = grant(None, 99.00, reason="loyalty-3yr", by=999, discord_id=777)
    assert bal == 99.00
    assert get_balance("discord:777") == 99.00
    assert resolve_by_discord(777) == "discord:777"
    assert get_tv_username(777) is None


def test_use_reduces_balance(credit_file):
    grant("trader_joe", 100, by=999)
    bal = use("TRADER_JOE", 37.80, reason="renewal", by=999)
    assert bal == 62.20
    assert get_balance("trader_joe") == 62.20


def test_use_insufficient_raises_and_keeps_balance(credit_file):
    grant("trader_joe", 50, by=999)
    with pytest.raises(InsufficientCredit) as exc_info:
        use("trader_joe", 50.01, by=999)
    assert exc_info.value.balance == 50.00
    assert exc_info.value.requested == 50.01
    assert get_balance("trader_joe") == 50.00  # 未扣款


def test_use_unknown_tv_raises_insufficient(credit_file):
    with pytest.raises(InsufficientCredit) as exc_info:
        use("nobody_here", 5, by=999)
    assert exc_info.value.balance == 0.00


def test_use_exact_balance_ok(credit_file):
    grant("trader_joe", 50, by=999)
    assert use("trader_joe", 50, by=999) == 0.00


def test_use_rejects_non_positive(credit_file):
    grant("trader_joe", 50, by=999)
    with pytest.raises(ValueError):
        use("trader_joe", 0, by=999)
    assert get_balance("trader_joe") == 50.00


def test_balance_unknown_tv_is_zero(credit_file):
    assert get_balance("ghost_tv") == 0.0


def test_recent_txns_order_and_limit(credit_file):
    grant("trader_joe", 10, reason="a", by=999)
    grant("trader_joe", 20, reason="b", by=999)
    use("trader_joe", 5, reason="c", by=999)
    txns = recent_txns("TRADER_JOE", 5)
    assert [t["type"] for t in txns] == ["use", "grant", "grant"]
    assert txns[0]["reason"] == "c"
    assert len(recent_txns("trader_joe", 2)) == 2
    assert recent_txns("ghost_tv") == []


# ── 绑定 / 换绑 ───────────────────────────────────────────────────────────

def test_link_tv(credit_file):
    assert link_tv(111, "  Trader_Joe ") == "Trader_Joe"
    assert resolve_by_discord(111) == "trader_joe"
    assert get_tv_username(111) == "Trader_Joe"


def test_link_tv_rejects_empty(credit_file):
    with pytest.raises(ValueError):
        link_tv(111, "   ")


def test_link_tv_conflict_raises(credit_file):
    link_tv(111, "aaa")
    with pytest.raises(ValueError):
        link_tv(111, "bbb")  # 同一 discord 已绑定别的 TV → 拒绝，避免账乱
    assert resolve_by_discord(111) == "aaa"


def test_relink_discord_moves_balance_with_tv(credit_file):
    grant("aaa", 50, by=999, discord_id=111)
    assert resolve_by_discord(111) == "aaa"
    bound = relink_discord("AAA", 222)
    assert bound == "aaa"
    assert resolve_by_discord(222) == "aaa"
    assert resolve_by_discord(111) is None  # 旧映射清除
    assert get_balance("aaa") == 50.00  # credit 跟着 TV 走
    assert get_tv_username(222) == "aaa"


def test_relink_discord_unknown_tv_raises(credit_file):
    with pytest.raises(ValueError):
        relink_discord("ghost_tv", 222)


def test_relink_discord_conflict_raises(credit_file):
    link_tv(111, "aaa")
    link_tv(222, "bbb")
    with pytest.raises(ValueError):
        relink_discord("aaa", 222)  # 222 已绑定 bbb


def test_resolve_by_discord_unbound_is_none(credit_file):
    assert resolve_by_discord(424242) is None


def test_state_persists_across_loads(credit_file):
    grant("trader_joe", 25.50, reason="x", by=999, discord_id=111)
    # 重新读文件（模拟进程重启）
    assert get_balance("trader_joe") == 25.50
    assert resolve_by_discord(111) == "trader_joe"
    assert len(recent_txns("trader_joe")) == 1


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
async def test_relink_discord_rejects_non_admin():
    cog = _cog()
    ctx = MagicMock()
    ctx.permissions = discord.Permissions(administrator=False)
    with pytest.raises(commands.MissingPermissions):
        for check in cog.relink_discord_cmd.checks:
            result = check(ctx)
            if hasattr(result, "__await__"):
                await result


@pytest.mark.asyncio
async def test_admin_checks_pass():
    cog = _cog()
    for cmd in (cog.grant_credit, cog.use_credit, cog.link_tv_cmd,
                cog.relink_discord_cmd):
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
    link_tv(111, "trader_joe")
    ctx, member = _ctx(), _member()
    await cog.grant_credit.callback(cog, ctx, member, "41.40", reason="black friday")
    assert get_balance("trader_joe") == 41.40
    member.send.assert_awaited_once()
    dm_text = member.send.await_args.args[0]
    assert "$41.40" in dm_text and "black friday" in dm_text
    assert "trader_joe" in dm_text
    reply_text = ctx.reply.await_args.args[0]
    assert "$41.40" in reply_text and "trader_joe" in reply_text


@pytest.mark.asyncio
async def test_grant_credit_unlinked_rejected_no_account(credit_file):
    """未绑定 TV 的用户：报错，不静默建账，避免账乱。"""
    cog = _cog()
    ctx, member = _ctx(), _member()
    await cog.grant_credit.callback(cog, ctx, member, "41.40")
    reply_text = ctx.reply.await_args.args[0]
    assert "绑定" in reply_text and "link_tv" in reply_text
    assert resolve_by_discord(111) is None  # 没有建任何账户
    member.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_grant_credit_dm_blocked_still_ok(credit_file):
    cog = _cog()
    link_tv(111, "trader_joe")
    ctx, member = _ctx(), _member(dm_blocked=True)
    await cog.grant_credit.callback(cog, ctx, member, "10")
    assert get_balance("trader_joe") == 10.00
    ctx.reply.assert_awaited_once()  # 不抛异常，照常回复


@pytest.mark.asyncio
async def test_grant_credit_bad_amount(credit_file):
    cog = _cog()
    link_tv(111, "trader_joe")
    ctx, member = _ctx(), _member()
    await cog.grant_credit.callback(cog, ctx, member, "abc")
    assert get_balance("trader_joe") == 0.0
    assert "无效" in ctx.reply.await_args.args[0]


@pytest.mark.asyncio
async def test_use_credit_happy_path(credit_file):
    cog = _cog()
    link_tv(111, "trader_joe")
    grant("trader_joe", 100, by=999)
    ctx, member = _ctx(), _member()
    await cog.use_credit.callback(cog, ctx, member, "37.8", reason="renewal")
    assert get_balance("trader_joe") == 62.20
    dm_text = member.send.await_args.args[0]
    assert "$37.80" in dm_text and "renewal" in dm_text


@pytest.mark.asyncio
async def test_use_credit_unlinked_rejected(credit_file):
    cog = _cog()
    ctx, member = _ctx(), _member()
    await cog.use_credit.callback(cog, ctx, member, "10")
    assert "绑定" in ctx.reply.await_args.args[0]
    member.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_use_credit_insufficient_no_deduction(credit_file):
    cog = _cog()
    link_tv(111, "trader_joe")
    grant("trader_joe", 10, by=999)
    ctx, member = _ctx(), _member()
    await cog.use_credit.callback(cog, ctx, member, "99")
    assert get_balance("trader_joe") == 10.00  # 未扣款
    assert "余额不足" in ctx.reply.await_args.args[0]
    member.send.assert_not_awaited()  # 失败不发 DM


@pytest.mark.asyncio
async def test_link_tv_cmd(credit_file):
    cog = _cog()
    ctx, member = _ctx(), _member()
    await cog.link_tv_cmd.callback(cog, ctx, member, "trader_joe")
    assert resolve_by_discord(111) == "trader_joe"
    assert "trader_joe" in ctx.reply.await_args.args[0]


@pytest.mark.asyncio
async def test_relink_discord_cmd(credit_file):
    cog = _cog()
    link_tv(111, "trader_joe")
    grant("trader_joe", 41.40, by=999)
    ctx, new_member = _ctx(), _member(uid=222)
    await cog.relink_discord_cmd.callback(cog, ctx, "trader_joe", new_member)
    reply_text = ctx.reply.await_args.args[0]
    assert "换绑" in reply_text and "trader_joe" in reply_text
    assert resolve_by_discord(222) == "trader_joe"
    assert resolve_by_discord(111) is None
    assert get_balance("trader_joe") == 41.40


@pytest.mark.asyncio
async def test_relink_discord_cmd_missing_args(credit_file):
    cog = _cog()
    ctx = _ctx()
    await cog.relink_discord_cmd.callback(cog, ctx, "", None)
    assert "用法" in ctx.reply.await_args.args[0]


@pytest.mark.asyncio
async def test_my_credit_ephemeral(credit_file):
    cog = _cog()
    link_tv(111, "Trader_Joe")
    grant("trader_joe", 41.40, reason="black friday", by=999)
    use("trader_joe", 10, reason="renewal", by=999)
    interaction = MagicMock()
    interaction.user.id = 111
    interaction.response.send_message = AsyncMock()
    await cog.my_credit.callback(cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.await_args.kwargs
    assert kwargs.get("ephemeral") is True
    text = interaction.response.send_message.await_args.args[0]
    assert "$31.40" in text
    assert "Trader_Joe" in text
    assert "black friday" in text and "renewal" in text


# ── 退化账户合并（bug 修复回归） ─────────────────────────────────────────

def test_link_tv_merges_fallback_account(credit_file):
    """import 建的退化账户（TV 未知），后来知道 TV 后绑定：余额/流水迁入 TV 账户。"""
    grant(None, 99.00, reason="loyalty-3yr", by="import_script", discord_id=777)
    bound = link_tv(777, "Real_TV")
    assert bound == "Real_TV"
    assert resolve_by_discord(777) == "real_tv"
    assert get_balance("real_tv") == 99.00
    assert get_balance("discord:777") == 0.0  # 退化账户已删除
    txns = recent_txns("real_tv", 5)
    assert len(txns) == 1 and txns[0]["reason"] == "loyalty-3yr"


def test_grant_merges_fallback_account(credit_file):
    """grant 带 discord_id 撞上退化账户：自动合并，不抛错。"""
    grant(None, 50.00, by="import_script", discord_id=777)
    bal = grant("Real_TV", 10.00, reason="black friday", by=999, discord_id=777)
    assert bal == 60.00
    assert resolve_by_discord(777) == "real_tv"


def test_relink_discord_merges_fallback_account(credit_file):
    grant(None, 25.00, by="import_script", discord_id=777)
    grant("real_tv", 5.00, by=999)  # TV 账户先存在
    bound = relink_discord("real_tv", 777)
    assert bound == "real_tv"
    assert get_balance("real_tv") == 30.00
    assert resolve_by_discord(777) == "real_tv"


def test_genuine_conflict_still_raises(credit_file):
    """真冲突（discord 已绑定另一个 TV）仍然拒绝，不静默合并。"""
    link_tv(111, "aaa")
    grant("bbb", 5.00, by=1, discord_id=222)
    with pytest.raises(ValueError):
        link_tv(111, "bbb")  # 111 已绑定 aaa
    with pytest.raises(ValueError):
        relink_discord("bbb", 111)  # 111 已绑定 aaa
    with pytest.raises(ValueError):
        grant("ccc", 5.00, by=1, discord_id=111)  # grant 换绑冲突也拒绝
    assert resolve_by_discord(111) == "aaa"
    assert get_balance("aaa") == 0.0 and get_balance("bbb") == 5.00


def test_merged_txns_keep_chronological_order(credit_file):
    grant("real_tv", 10.00, reason="first", by=1)
    grant(None, 20.00, reason="second", by=1, discord_id=777)
    link_tv(777, "real_tv")
    txns = recent_txns("real_tv", 10)
    assert [t["reason"] for t in txns] == ["second", "first"]


# ── 规范化 ────────────────────────────────────────────────────────────────

def test_tv_key_nfc_normalization(credit_file):
    """同一视觉用户名（NFC vs NFD）必须映射到同一主键。"""
    import unicodedata
    nfc = unicodedata.normalize("NFC", "café_trader")
    nfd = unicodedata.normalize("NFD", "café_trader")
    assert nfc != nfd  # 前提：两种形式确实不同
    grant(nfc, 10.00, by=1)
    grant(nfd, 5.00, by=1)
    assert get_balance("café_trader") == 15.00


def test_use_unknown_tv_leaves_no_phantom_account(credit_file):
    """use() 在未知 TV 上抛 InsufficientCredit，且不落盘幽灵空账户。"""
    with pytest.raises(InsufficientCredit):
        use("Nobody_Here", 5, by=1)
    assert get_account_info("nobody_here") is None
    assert resolve_by_discord(999999) is None


def test_concurrent_grants_no_lost_update(credit_file):
    """多线程并发 grant：锁保证不丢账。"""
    import threading
    errors = []

    def worker():
        try:
            for _ in range(10):
                grant("concurrent_tv", 1.00, by=1)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert get_balance("concurrent_tv") == 50.00


@pytest.mark.asyncio
async def test_my_credit_unlinked_prompts_binding(credit_file):
    cog = _cog()
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()
    await cog.my_credit.callback(cog, interaction)
    kwargs = interaction.response.send_message.await_args.kwargs
    assert kwargs.get("ephemeral") is True
    text = interaction.response.send_message.await_args.args[0]
    assert "群主" in text or "绑定" in text
