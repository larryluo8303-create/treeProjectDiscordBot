"""bigTreeSignal credit 台账 Discord 命令。

主键是 **TradingView 用户名**（用户换 Discord 账号时 credit 跟着 TV id 走）。
Discord ID 只用于定位用户：命令先按 ``resolve_by_discord`` 反查到 TV 主键。

- ``!grant_credit @成员 <金额> [原因]``（仅管理员）：按 TV 主键发放；
  未绑定 TV 时报错，**不**静默建 Discord 主键账户（避免账乱）。
- ``!use_credit @成员 <金额> [原因]``（仅管理员）：按 TV 主键抵扣。
- ``!link_tv @成员 <TV用户名>``（仅管理员）：绑定 TradingView ID。
- ``!relink_discord <TV用户名> @成员``（仅管理员）：TV 账户换绑新 Discord。
- ``/my_credit``（所有用户）：ephemeral 显示自己的余额 + 最近 5 笔明细。

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
    get_account_info,
    grant,
    link_tv,
    recent_txns,
    relink_discord,
    resolve_by_discord,
    use,
)

logger = logging.getLogger(__name__)

GRANT_CONFIRM_DM = (
    "💰 你的 bigTreeSignal credit 账户（TradingView：`{tv}`）收到 "
    "**${amount:.2f}**{reason}，当前余额 **${balance:.2f}**。\n"
    "credit 可积累、不过期，可在 ETF / 个股版之间互转，用于将来续费或升级。"
)

USE_CONFIRM_DM = (
    "💰 你的 bigTreeSignal credit 账户（TradingView：`{tv}`）已抵扣 "
    "**${amount:.2f}**{reason}，当前余额 **${balance:.2f}**。"
)


def _parse_amount(raw: str) -> float | None:
    """解析金额字符串；非法/非正数返回 None。"""
    try:
        cleaned = (raw or "").strip().replace("$", "").replace(",", "")
        amount = round(float(cleaned), 2)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def _account_label(info: dict, key: str) -> str:
    """账户展示名：有 TV 显示 TV 名；退化账户（discord:<id>）显示 Discord ID
    并注明未绑定 TV，避免 DM 里出现 "TradingView：`discord:777`" 这种迷惑文案。"""
    tv = (info or {}).get("tv_username")
    if tv:
        return tv
    if key.startswith("discord:"):
        return f"Discord:{key.split(':', 1)[1]}（未绑定 TV）"
    return key


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
    """bigTreeSignal credit 台账：发放、抵扣、查询、TV 绑定/换绑。"""

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
        key = resolve_by_discord(member.id)
        if key is None:
            await ctx.reply(
                f"❌ {member.mention} 尚未绑定 TradingView ID。\n"
                "credit 跟 TV id 走，不跟 Discord 账号走——请先执行 "
                f"`!link_tv {member.mention} <TV用户名>` 绑定后再发放。",
                mention_author=False,
            )
            return
        reason = (reason or "").strip()[:200]
        try:
            balance = grant(key, amount, reason=reason, by=ctx.author.id)
        except ValueError as exc:
            await ctx.reply(f"发放失败：{exc}", mention_author=False)
            return
        info = get_account_info(key) or {}
        tv = _account_label(info, key)
        reason_txt = f"（{reason}）" if reason else ""
        await self._safe_dm(
            member,
            GRANT_CONFIRM_DM.format(
                tv=tv, amount=amount, balance=balance, reason=reason_txt
            ),
        )
        await ctx.reply(
            f"✅ 已发放 **${amount:.2f}** credit 给 `{tv}`（{member.mention}），"
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
        key = resolve_by_discord(member.id)
        if key is None:
            await ctx.reply(
                f"❌ {member.mention} 尚未绑定 TradingView ID，"
                "没有可抵扣的 credit 账户。",
                mention_author=False,
            )
            return
        reason = (reason or "").strip()[:200]
        try:
            balance = use(key, amount, reason=reason, by=ctx.author.id)
        except InsufficientCredit as exc:
            label = _account_label(get_account_info(key), key)
            await ctx.reply(
                f"❌ 余额不足：`{label}` 当前余额 **${exc.balance:.2f}**，"
                f"要抵扣 **${exc.requested:.2f}**。未扣款。",
                mention_author=False,
            )
            return
        except ValueError as exc:
            await ctx.reply(f"抵扣失败：{exc}", mention_author=False)
            return
        info = get_account_info(key) or {}
        tv = _account_label(info, key)
        reason_txt = f"（{reason}）" if reason else ""
        await self._safe_dm(
            member,
            USE_CONFIRM_DM.format(tv=tv, amount=amount, balance=balance,
                                  reason=reason_txt),
        )
        await ctx.reply(
            f"✅ 已从 `{tv}`（{member.mention}）抵扣 **${amount:.2f}** credit，"
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
            f"✅ 已绑定 {member.mention} 的 TradingView 用户名：`{bound}`。"
            "此后 credit 都记在这个 TV id 名下。",
            mention_author=False,
        )

    @commands.command(name="relink_discord")
    @commands.has_permissions(administrator=True)
    async def relink_discord_cmd(
        self,
        ctx: commands.Context,
        tv_username: str = "",
        member: discord.Member | None = None,
    ) -> None:
        """用法：!relink_discord <TV用户名> @成员（用户换 Discord 账号时用）"""
        tv_username = (tv_username or "").strip()
        if not tv_username or member is None:
            await ctx.reply(
                "用法：`!relink_discord <TV用户名> @成员`", mention_author=False
            )
            return
        try:
            bound = relink_discord(tv_username, member.id)
        except ValueError as exc:
            await ctx.reply(f"换绑失败：{exc}", mention_author=False)
            return
        await ctx.reply(
            f"✅ 已将 `{bound}` 换绑到 {member.mention}，"
            "credit 余额跟着 TV id 走，不受影响。",
            mention_author=False,
        )

    @app_commands.command(name="my_credit", description="查看我的 bigTreeSignal credit 余额")
    async def my_credit(self, interaction: discord.Interaction) -> None:
        uid = interaction.user.id
        key = resolve_by_discord(uid)
        if key is None:
            await interaction.response.send_message(
                "💰 未找到你的 credit 账户。\n"
                "credit 跟 TradingView ID 走——请联系群主绑定你的 TV 用户名后再查询。",
                ephemeral=True,
            )
            return
        info = get_account_info(key) or {}
        balance = info.get("balance", 0.0)
        tv = _account_label(info, key)
        txns = recent_txns(key, 5)
        lines = [
            f"💰 当前余额：**${balance:.2f}** USD",
            f"TradingView：`{tv}`",
            "",
            "最近 5 笔：",
            _fmt_txns(txns),
            "",
            "credit 可积累、不过期，可在 ETF / 个股版之间互转，用于续费或升级。",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
