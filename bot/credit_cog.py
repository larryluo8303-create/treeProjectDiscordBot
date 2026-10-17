"""bigTreeSignal credit 台账 Discord 命令。

- ``!grant_credit @成员 <金额> [原因]``（仅管理员）：发放 credit，DM 通知用户。
- ``!use_credit @成员 <金额> [原因]``（仅管理员）：抵扣 credit，余额不足时
  报错且不扣款，DM 通知用户。
- ``/my_credit``（所有用户）：ephemeral 显示自己的余额 + 最近 5 笔明细。
- ``!link_tv @成员 <TV用户名>``（仅管理员）：绑定 TradingView ID。

所有 DM 通知失败都不抛异常（用户关闭私信也不能崩）。
金额单位 USD。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.credit import (
    InsufficientCredit,
    get_balance,
    get_tv_username,
    grant,
    link_tv,
    recent_txns,
    use,
)

logger = logging.getLogger(__name__)

GRANT_CONFIRM_DM = (
    "💰 你的 bigTreeSignal credit 账户收到 **${amount:.2f}**{reason}，"
    "当前余额 **${balance:.2f}**。\n"
    "credit 可积累、不过期，可在 ETF / 个股版之间互转，用于将来续费或升级。"
)

USE_CONFIRM_DM = (
    "💰 你的 bigTreeSignal credit 账户已抵扣 **${amount:.2f}**{reason}，"
    "当前余额 **${balance:.2f}**。"
)


def _parse_amount(raw: str) -> float | None:
    """解析金额字符串；非法/非正数返回 None。"""
    try:
        cleaned = (raw or "").strip().replace("$", "").replace(",", "")
        amount = round(float(cleaned), 2)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def _fmt_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "?"


def _fmt_txns(txns: list[dict]) -> str:
    if not txns:
        return "暂无交易记录。"
    lines = []
    for t in txns:
        sign = "+" if t.get("type") == "grant" else "-"
        reason = t.get("reason") or ""
        suffix = f"（{reason}）" if reason else ""
        lines.append(
            f"{_fmt_ts(t.get('ts', 0))} {sign}${t.get('amount', 0):.2f}{suffix}"
        )
    return "\n".join(lines)


class CreditCog(commands.Cog):
    """bigTreeSignal credit 台账：发放、抵扣、查询、TV 绑定。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _safe_dm(self, member: discord.Member, text: str) -> None:
        """DM 通知；用户关闭私信时只记 log，绝不抛异常。"""
        try:
            await member.send(text)
        except discord.Forbidden:
            logger.info("credit: DM blocked for %s", member.id)
        except Exception as exc:
            logger.warning("credit: DM to %s failed: %s", member.id, exc)

    @commands.command(name="grant_credit")
    @commands.has_permissions(administrator=True)
    async def grant_credit(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        amount_raw: str = "",
        *,
        reason: str = "",
    ) -> None:
        """用法：!grant_credit @成员 <金额> [原因]"""
        if member is None:
            await ctx.reply(
                "用法：`!grant_credit @成员 <金额> [原因]`", mention_author=False
            )
            return
        amount = _parse_amount(amount_raw)
        if amount is None:
            await ctx.reply(
                "金额无效，请输入大于 0 的数字（USD）。", mention_author=False
            )
            return
        reason = (reason or "").strip()[:200]
        try:
            balance = grant(member.id, amount, reason=reason, by=ctx.author.id)
        except ValueError as exc:
            await ctx.reply(f"发放失败：{exc}", mention_author=False)
            return
        reason_txt = f"（{reason}）" if reason else ""
        await self._safe_dm(
            member,
            GRANT_CONFIRM_DM.format(
                amount=amount, balance=balance, reason=reason_txt
            ),
        )
        await ctx.reply(
            f"✅ 已发放 **${amount:.2f}** credit 给 {member.mention}，"
            f"当前余额 **${balance:.2f}**。",
            mention_author=False,
        )

    @commands.command(name="use_credit")
    @commands.has_permissions(administrator=True)
    async def use_credit(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        amount_raw: str = "",
        *,
        reason: str = "",
    ) -> None:
        """用法：!use_credit @成员 <金额> [原因]"""
        if member is None:
            await ctx.reply(
                "用法：`!use_credit @成员 <金额> [原因]`", mention_author=False
            )
            return
        amount = _parse_amount(amount_raw)
        if amount is None:
            await ctx.reply(
                "金额无效，请输入大于 0 的数字（USD）。", mention_author=False
            )
            return
        reason = (reason or "").strip()[:200]
        try:
            balance = use(member.id, amount, reason=reason, by=ctx.author.id)
        except InsufficientCredit as exc:
            await ctx.reply(
                f"❌ 余额不足：{member.mention} 当前余额 **${exc.balance:.2f}**，"
                f"要抵扣 **${exc.requested:.2f}**。未扣款。",
                mention_author=False,
            )
            return
        except ValueError as exc:
            await ctx.reply(f"抵扣失败：{exc}", mention_author=False)
            return
        reason_txt = f"（{reason}）" if reason else ""
        await self._safe_dm(
            member,
            USE_CONFIRM_DM.format(amount=amount, balance=balance, reason=reason_txt),
        )
        await ctx.reply(
            f"✅ 已从 {member.mention} 抵扣 **${amount:.2f}** credit，"
            f"当前余额 **${balance:.2f}**。",
            mention_author=False,
        )

    @commands.command(name="link_tv")
    @commands.has_permissions(administrator=True)
    async def link_tv_cmd(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        tv_username: str = "",
    ) -> None:
        """用法：!link_tv @成员 <TradingView用户名>"""
        tv_username = (tv_username or "").strip()
        if member is None or not tv_username:
            await ctx.reply(
                "用法：`!link_tv @成员 <TradingView用户名>`", mention_author=False
            )
            return
        try:
            bound = link_tv(member.id, tv_username)
        except ValueError as exc:
            await ctx.reply(f"绑定失败：{exc}", mention_author=False)
            return
        await ctx.reply(
            f"✅ 已绑定 {member.mention} 的 TradingView 用户名：`{bound}`。",
            mention_author=False,
        )

    @app_commands.command(name="my_credit", description="查看我的 bigTreeSignal credit 余额")
    async def my_credit(self, interaction: discord.Interaction) -> None:
        uid = interaction.user.id
        balance = get_balance(uid)
        tv = get_tv_username(uid)
        txns = recent_txns(uid, 5)
        lines = [f"💰 当前余额：**${balance:.2f}** USD"]
        if tv:
            lines.append(f"TradingView：`{tv}`")
        lines.append("")
        lines.append("最近 5 笔：")
        lines.append(_fmt_txns(txns))
        lines.append("")
        lines.append("credit 可积累、不过期，可在 ETF / 个股版之间互转，用于续费或升级。")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
