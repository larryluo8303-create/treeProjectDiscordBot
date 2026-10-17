"""「信号体验」免费试用 cog（v3：点击即开通）。

- ``!试用`` / 推广 DM 里的 ✅ 按钮（custom_id=``trial_join``）：
  资格三检查（非付费/终身一次/账号≥30天）+ 活动有效期检查 →
  立即发放「信号体验」身份组（会员频道只读，2027 年前有效）→
  DM 用户开通确认 + TradingView 指引（私信群主发分享截图 + TV 用户名）。
  30 天计时从发放开始。
- ``!tvdone @成员 <TV用户名>``（仅管理员）：群主在 TradingView 手动开通后执行 →
  记录 tv_username/tv_granted → DM 用户"TV 权限已开通"。
- 每小时 loop：到期回收（收回试用组、挂「体验过期」标记组、发 Day30 到期通知）
  + 转化 drip（started_at +1/7/14/21/25 天发 DM；Day30 由到期处理发送）。
- 行为触发：on_member_join / 首条群消息 / on_reaction_add 符合条件发一次
  promo DM（带 ✅ 报名按钮）。
- STOP 退订：DM 里回复 STOP/退订 等关键词 → 记入退订名单并同步给群发脚本。

TRIAL30_ENABLED=False（默认）时，命令与触发器全部静默跳过，只有 STOP
监听生效。活动过期（TRIAL_CAMPAIGN_END，默认 2026-12-31）后不再发放新试用。
所有 Discord 特权调用都按仓库惯例降级：discord.Forbidden 只记
warning，绝不抛错。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from bot.timed_roles import _parse_ts, is_paid_member
from bot.trial_config import (
    BROADCAST_STATE_FILE,
    PAID_ROLE_IDS,
    TRIAL30_DAYS,
    TRIAL30_ENABLED,
    TRIAL30_EXPIRED_ROLE_NAME,
    TRIAL30_INVITE_LINK,
    TRIAL30_MIN_ACCOUNT_AGE_DAYS,
    TRIAL30_ROLE_NAME,
    campaign_active,
)
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

TRIAL30_STATE_FILE = data_path(os.getenv("TRIAL30_STATE_FILE", "data/trial30.json"))

# Drip 计划：started_at 之后第 N 天发 DM。Day 30 由到期处理发送（即到期
# 通知），drip 循环只负责 1/7/14/21/25。
DRIP_DAYS = (1, 7, 14, 21, 25, 30)
_DRIP_LOOP_DAYS = (1, 7, 14, 21, 25)

STOP_KEYWORDS = {"stop", "退订", "取消", "unsubscribe", "td"}


# ── 推广 DM 文案 ─────────────────────────────────────────────────────────
# 逐字复制自 ~/workspace/bot-ops/dm_broadcast.py 的 build_dm_text()
# （v3：点击 ✅ 即开通，终稿用户已审）。两处手动同步：
# 改文案时记得两边一起改。
TRIAL30_PROMO_TEMPLATE = (
    "Hi {name}，我是 bigTreeSignal 的小助手🌲\n"
    "\n"
    "🎉 为期一个月的免费信号体验活动开始了！\n"
    "\n"
    "bigTreeSignal ETF 信号（TradingView invite-only 指标）+ 会员频道完整内容，"
    "**免费体验 30 天**。\n"
    "\n"
    "📺 信号使用教程：https://www.youtube.com/watch?v=uykQwiDW55k\n"
    "\n"
    "想参加？点击下面的 ✅ 按钮，自动为你开通。\n"
    "\n"
    "说明：每人终身只能参加一次，现有付费会员已自动排除。\n"
    "\n"
    "不想再收到这类推广消息？直接回复 STOP，我就不再打扰你。"
)

# 报名按钮 custom_id（群发 DM / 行为触发 DM 共用）。
TRIAL_JOIN_BUTTON_ID = "trial_join"
TRIAL_JOIN_BUTTON_LABEL = "✅ 我要参加免费试用"


# ── 转化 drip 文案（简短中文，用户可直接改） ────────────────────────────────
TRIAL30_DRIP: dict[int, str] = {
    1: (
        "🌲 **免费试用第 1 天**\n"
        "欢迎体验 bigTreeSignal 信号！\n"
        "想要 TradingView 上的 ETF 指标？在群里点击群主 @bigtreesignal 的头像私信他，发送：\n"
        "① 你把邀请链接分享到其他群 / 社交媒体的截图\n"
        "② 你的 TradingView 用户名\n"
        "群主审核后为你开通 📈\n"
        "今天可以先看：每日 AI 共振日报 + 盘前简报，感受一下三家信号"
        "（TradingAgents / FinRobot / 对冲基金）的共振逻辑。\n"
        "有问题随时在群里问 🙌"
    ),
    7: (
        "🌲 **免费试用第 7 天**\n"
        "一周过去了，这周的 AI 共振日报有没有帮你避开坑、抓住机会？\n"
        "小提示：盘中异动提醒是短线党的利器，记得打开通知 🔔"
    ),
    14: (
        "🌲 **免费试用第 14 天**\n"
        "试用过半！除了日报和盘前简报，会员频道的完整内容、历史信号复盘"
        "都值得翻一翻。\n"
        "觉得有用，欢迎推荐朋友一起来试用～"
    ),
    21: (
        "🌲 **免费试用第 21 天**\n"
        "还剩 9 天。很多会员反馈：跟着信号做纪律交易，心态稳了很多。\n"
        "转正后信号不间断，想继续的话可以提前了解一下付费会员 💳"
    ),
    25: (
        "⚠️ **试用还有 5 天到期**\n"
        "你的免费试用即将结束。到期后试用身份组自动收回，会员频道将不可见。\n"
        "想无缝续上？现在转付费会员，信号不中断 👉 有问题在群里 @我"
    ),
    30: (
        "🌲 **免费试用已到期**\n"
        "30 天体验结束，试用身份组已收回，感谢体验！\n"
        "如果这 30 天的信号对你有帮助，欢迎转为付费会员继续接收信号。\n"
        "后会有期，祝交易顺利 🙏"
    ),
}

# 报名/!试用 通过后的开通确认 DM（v3：点击即开通，终稿用户已审）。
TRIAL30_GRANTED_CONFIRM = (
    "✅ 已为你开通「信号体验」30 天！会员频道已可见。\n"
    "\n"
    "想要 TradingView 上的 ETF 指标权限？在群里点击群主 @bigtreesignal 的头像私信他，发送：\n"
    "① 你把邀请链接分享到其他群 / 社交媒体的截图\n"
    "② 你的 TradingView 用户名\n"
    "邀请链接：\n"
    f"{TRIAL30_INVITE_LINK}\n"
    "群主审核后为你开通 📈\n"
    "\n"
    "📺 信号使用教程：https://www.youtube.com/watch?v=uykQwiDW55k"
)

# !tvdone 执行后发给用户的确认 DM。
TRIAL30_TVDONE_CONFIRM = (
    "✅ **TradingView 权限已开通！**\n\n"
    "群主已在 TradingView 上为你开通 bigTreeSignal ETF version 指标权限，"
    "刷新页面即可使用 📈\n"
    "📺 信号使用教程：https://www.youtube.com/watch?v=uykQwiDW55k\n"
    "你的「信号体验」试用继续有效，到期后自动结束。"
)

# 活动过期提示。
TRIAL30_CAMPAIGN_ENDED = (
    "本期免费信号体验活动已结束（2026 年底截止），感谢关注 🙏"
)

_ELIGIBILITY_FAIL_TEXT = {
    "paid": "你已是付费会员，无需领取试用 🙏\n\n🎉 11月黑五促销：原价9折 + 10% credit返还，现在不需要做什么，到时我会通知你！",
    "claimed": "每人终身只能领取一次免费试用，你已经领过了。",
    "account_too_new": (
        f"Discord 账号注册满 {TRIAL30_MIN_ACCOUNT_AGE_DAYS} 天后才能领取免费试用。"
    ),
}


# ── 纯函数（可单元测试） ───────────────────────────────────────────────────

def check_trial_eligibility(
    *,
    has_paid_role: bool,
    already_claimed: bool,
    account_created_at: datetime | None,
    now: datetime | None = None,
    min_account_age_days: int = TRIAL30_MIN_ACCOUNT_AGE_DAYS,
) -> tuple[bool, str]:
    """试用资格三检查。返回 (通过, 原因码)，原因码 ∈ ok/paid/claimed/account_too_new。"""
    now = now or datetime.now(timezone.utc)
    if has_paid_role:
        return False, "paid"
    if already_claimed:
        return False, "claimed"
    if account_created_at is None:
        return False, "account_too_new"
    created = account_created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if (now - created).total_seconds() < min_account_age_days * 86400:
        return False, "account_too_new"
    return True, "ok"


def due_drips(
    started_at: datetime,
    now: datetime | None = None,
    drip_sent: list[int] | None = None,
    drip_days: tuple[int, ...] = DRIP_DAYS,
) -> list[int]:
    """返回已到期但尚未发送的 drip 天数（升序）。纯函数。"""
    now = now or datetime.now(timezone.utc)
    start = started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    sent = set(drip_sent or [])
    return [
        d for d in drip_days
        if d not in sent and start + timedelta(days=d) <= now
    ]


def is_stop_message(content: str | None) -> bool:
    """DM 内容是否为退订关键词（纯函数）。"""
    return (content or "").strip().lower() in STOP_KEYWORDS


def promo_gate(
    uid: int | str,
    *,
    has_paid_role: bool,
    already_claimed: bool,
    account_created_at: datetime | None,
    state: dict,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """能否发 promo DM。返回 (可以, 原因码)。纯函数。"""
    uid = str(uid)
    if uid in set(state.get("opt_out", [])):
        return False, "opt_out"
    ok, reason = check_trial_eligibility(
        has_paid_role=has_paid_role,
        already_claimed=already_claimed,
        account_created_at=account_created_at,
        now=now,
    )
    if not ok:
        return False, reason
    if state.get("claimed", {}).get(uid, {}).get("promo_dm_sent"):
        return False, "promo_sent"
    return True, "ok"


def drip_gate(uid: int | str, day: int, state: dict) -> tuple[bool, str]:
    """能否发第 day 天的 drip DM。返回 (可以, 原因码)。纯函数。"""
    uid = str(uid)
    if uid in set(state.get("opt_out", [])):
        return False, "opt_out"
    rec = state.get("claimed", {}).get(uid)
    if not rec:
        return False, "not_claimed"
    if not rec.get("role_granted"):
        return False, "not_granted"
    if day in (rec.get("drip_sent") or []):
        return False, "already_sent"
    return True, "ok"


# ── 状态持久化 ─────────────────────────────────────────────────────────────

def _new_state() -> dict:
    return {"claimed": {}, "opt_out": [], "seen_first_msg": []}


def load_trial30_state() -> dict:
    try:
        with open(TRIAL30_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        st = _new_state()
        if isinstance(data, dict):
            st["claimed"] = data.get("claimed") or {}
            st["opt_out"] = data.get("opt_out") or []
            st["seen_first_msg"] = data.get("seen_first_msg") or []
        return st
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _new_state()


def save_trial30_state(state: dict) -> None:
    atomic_json_write(TRIAL30_STATE_FILE, state, ensure_ascii=False, indent=2)


def _sync_opt_out_to_broadcast(uid: str) -> None:
    """把退订写入群发脚本的 state（opted_out 名单），best-effort，失败只记日志。"""
    try:
        path = BROADCAST_STATE_FILE
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = {}
        opted = data.setdefault("opted_out", [])
        if uid not in opted:
            opted.append(uid)
        users = data.setdefault("users", {})
        users.setdefault(uid, {})["status"] = "opted_out"
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        logger.info("trial30: synced opt-out %s to broadcast state", uid)
    except Exception as exc:
        logger.warning("trial30: broadcast opt-out sync failed: %s", exc)


# ── Discord 小工具 ─────────────────────────────────────────────────────────

async def _ensure_role(guild: discord.Guild, name: str) -> discord.Role | None:
    """get-or-create 身份组（mentionable=False，无额外权限）。失败返回 None。"""
    role = discord.utils.get(guild.roles, name=name)
    if role is not None:
        return role
    try:
        role = await guild.create_role(
            name=name, mentionable=False, reason=f"trial30: {name}"
        )
        logger.info("trial30: created role %r in guild %s", name, guild.id)
        return role
    except discord.Forbidden:
        logger.warning(
            "trial30: missing MANAGE_ROLES — cannot create role %r in guild %s",
            name, guild.id,
        )
        return None
    except Exception as exc:
        logger.warning("trial30: create_role %r failed: %s", name, exc)
        return None


async def _dm_user(bot: discord.Client, user_id: int, text: str) -> bool:
    """发 DM。用户关闭私信（Forbidden）时静默跳过，返回 False。"""
    user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except Exception as exc:
            logger.info("trial30: fetch_user %s failed: %s", user_id, exc)
            return False
    try:
        await user.send(text)
        return True
    except discord.Forbidden:
        return False  # 用户关闭了私信，静默跳过
    except Exception as exc:
        logger.warning("trial30: DM to %s failed: %s", user_id, exc)
        return False


class TrialCog(commands.Cog):
    """「免费试用30天」：领取、到期回收、转化 drip、行为触发、STOP 退订。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # 串行化 trial30.json 的所有读写：✅ 连点 / drip 循环 / 到期循环 /
        # promo 触发并发时，避免"先读-后写"丢失更新（lost update）或重复发放。
        # bot 为单进程，asyncio.Lock 足以保证互斥。
        self._state_lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._trial30_loop.is_running():
            self._trial30_loop.start()

    async def cog_unload(self) -> None:
        self._trial30_loop.cancel()

    # ── 每小时：到期回收 + 转化 drip ────────────────────────────────────

    @tasks.loop(hours=1)
    async def _trial30_loop(self) -> None:
        if not TRIAL30_ENABLED:
            return
        try:
            await self._process_expiries()
        except Exception as exc:
            logger.warning("trial30 loop: expiry pass failed: %s", exc)
        try:
            await self._process_drips()
        except Exception as exc:
            logger.warning("trial30 loop: drip pass failed: %s", exc)

    @_trial30_loop.before_loop
    async def _before_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ── v3：点击/!试用 即时发放（共用 _grant_trial） ──────────────────────

    async def _grant_trial(
        self, member: discord.Member, guild: discord.Guild, via: str = "unknown"
    ) -> tuple[bool, str]:
        """v3 核心：资格检查通过 → 立即发放「信号体验」组并开始计时。

        全程持有 ``self._state_lock``：把"检查资格→发组→落盘"做成原子操作。
        用户快速连点 ✅/``!试用`` 时，第二个请求会排队等待，看到已发放记录
        后返回 ``claimed``——不会重复发组、不会重置 ``started_at``、不会
        覆盖并发写入的状态。

        返回 (成功, 原因码)：ok / disabled / campaign_ended / paid /
        claimed / account_too_new / role_failed。
        """
        if not TRIAL30_ENABLED:
            return False, "disabled"
        if not campaign_active():
            return False, "campaign_ended"
        async with self._state_lock:
            state = load_trial30_state()
            uid = str(member.id)
            if uid in state["claimed"] and state["claimed"][uid].get("role_granted"):
                return False, "claimed"
            ok, reason = check_trial_eligibility(
                has_paid_role=self._has_paid_role(member),
                already_claimed=False,
                account_created_at=getattr(member, "created_at", None),
            )
            if not ok:
                return False, reason
            role = await _ensure_role(guild, TRIAL30_ROLE_NAME)
            if role is None:
                return False, "role_failed"
            try:
                if role not in member.roles:
                    await member.add_roles(
                        role, reason=f"trial30 grant ({TRIAL30_DAYS}d)"
                    )
            except discord.Forbidden:
                logger.warning(
                    "trial30: missing MANAGE_ROLES — cannot grant %r to %s",
                    TRIAL30_ROLE_NAME, uid,
                )
                return False, "role_failed"
            except Exception as exc:
                logger.warning("trial30: grant trial role to %s failed: %s", uid, exc)
                return False, "role_failed"
            now = datetime.now(timezone.utc)
            prev = state["claimed"].get(uid, {})
            state["claimed"][uid] = {
                "started_at": now.isoformat(),
                "expires_at": (now + timedelta(days=TRIAL30_DAYS)).isoformat(),
                "role_granted": True,
                "tv_username": None,
                "tv_granted": False,
                "drip_sent": [],
                "promo_dm_sent": True,
                "granted_via": prev.get("granted_via") or via,
                "guild_id": guild.id,
            }
            save_trial30_state(state)
            logger.info(
                "trial30: granted %dd trial to %s (via=%s)", TRIAL30_DAYS, uid, via
            )
            return True, "ok"

    @commands.command(name="试用")
    async def claim_trial(self, ctx: commands.Context) -> None:
        """在群里发送 !试用 → 资格检查通过 → 立即发放「信号体验」组。"""
        if not TRIAL30_ENABLED:
            return  # 安全开关关闭时静默跳过
        member = ctx.author
        if ctx.guild is None or not isinstance(member, discord.Member):
            await ctx.reply("请在群里发送 `!试用` 领取 🙂")
            return
        ok, reason = await self._grant_trial(member, ctx.guild, via="command")
        if not ok:
            if reason == "campaign_ended":
                await ctx.reply(TRIAL30_CAMPAIGN_ENDED, mention_author=False)
            elif reason == "claimed":
                await ctx.reply(
                    "每人终身只能参加一次，你已经领过了 🙂", mention_author=False
                )
            elif reason in _ELIGIBILITY_FAIL_TEXT:
                await ctx.reply(_ELIGIBILITY_FAIL_TEXT[reason], mention_author=False)
            elif reason == "role_failed":
                await ctx.reply(
                    "开通失败，请稍后重试或联系管理员。", mention_author=False
                )
            return
        try:
            await member.send(TRIAL30_GRANTED_CONFIRM)
        except discord.Forbidden:
            logger.info("trial30: grant-confirm DM blocked for %s", member.id)
            await ctx.reply(
                "✅ 已开通！你的私信关着，TradingView 指引发在这里：\n"
                + TRIAL30_GRANTED_CONFIRM,
                mention_author=False,
            )
            return
        except Exception as exc:
            logger.warning(
                "trial30: grant-confirm DM to %s failed: %s", member.id, exc
            )
        await ctx.reply(
            "✅ 已为你开通「信号体验」30 天！请查看私信完成 TradingView 步骤 🙂",
            mention_author=False,
        )

    # ── ✅ 报名按钮（群发 DM / 行为触发 DM 共用） ─────────────────────────

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """处理 trial_join 按钮点击：资格检查 → 即时发放。"""
        if interaction.type is not discord.InteractionType.component:
            return
        data = interaction.data or {}
        if data.get("custom_id") != TRIAL_JOIN_BUTTON_ID:
            return
        if not TRIAL30_ENABLED:
            try:
                await interaction.response.send_message(
                    "活动暂未开启。", ephemeral=True
                )
            except Exception:
                pass
            return
        user = interaction.user
        if user.bot:
            return
        # DM 里点按钮时 user 是 User 而非 Member：去各 guild 找成员身份
        member: discord.Member | None = None
        guild: discord.Guild | None = None
        if isinstance(user, discord.Member):
            member, guild = user, user.guild
        else:
            for g in self.bot.guilds:
                m = g.get_member(user.id)
                if m is not None:
                    member, guild = m, g
                    break
        if member is None or guild is None:
            try:
                await interaction.response.send_message(
                    "请先加入 bigTreeSignal Discord 服务器再报名 🙂",
                    ephemeral=True,
                )
            except Exception:
                pass
            return
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        ok, reason = await self._grant_trial(member, guild, via="button")
        followup = interaction.followup
        if not ok:
            msg = {
                "campaign_ended": TRIAL30_CAMPAIGN_ENDED,
                "claimed": "每人终身只能参加一次，你已经领过了 🙂",
                "paid": _ELIGIBILITY_FAIL_TEXT["paid"],
                "account_too_new": _ELIGIBILITY_FAIL_TEXT["account_too_new"],
                "role_failed": "开通失败，请稍后重试或联系管理员。",
                "disabled": "活动暂未开启。",
            }.get(reason, "开通失败，请稍后重试。")
            try:
                await followup.send(msg, ephemeral=True)
            except Exception:
                pass
            return
        try:
            await followup.send(TRIAL30_GRANTED_CONFIRM, ephemeral=True)
        except Exception:
            pass
        # 同时 DM 一份确认（含 TV 指引），followup 消息 15 分钟后不可见
        try:
            await member.send(TRIAL30_GRANTED_CONFIRM)
        except Exception:
            pass

    # ── !tvdone @成员 <TV用户名>（仅管理员：记录 TV 开通） ────────────────

    @commands.command(name="tvdone")
    @commands.has_permissions(administrator=True)
    async def tvdone(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        *,
        tv_username: str = "",
    ) -> None:
        """群主在 TradingView 手动开通后执行：记录 TV 用户名并 DM 用户确认。

        ``tv_username`` 为 keyword-only 参数：整行剩余部分整体捕获，
        TV 用户名含空格也不会被静默截断。
        """
        if not TRIAL30_ENABLED:
            return  # 安全开关关闭时静默跳过
        tv_username = (tv_username or "").strip()
        if member is None or not tv_username:
            await ctx.reply(
                "用法：`!tvdone @成员 <TradingView用户名>`",
                mention_author=False,
            )
            return
        if len(tv_username) > 50:
            await ctx.reply("TV 用户名过长（最多 50 字符），请检查。", mention_author=False)
            return
        uid = str(member.id)
        state = load_trial30_state()
        rec = state["claimed"].get(uid)
        if rec is None or not rec.get("role_granted"):
            # 兜底：该用户还没走报名流程，顺手补发身份组并开始计时
            ok, reason = await self._grant_trial(member, ctx.guild, via="tvdone")
            if not ok and reason != "claimed":
                await ctx.reply(
                    "开通失败（资格不通过或发组失败），请检查后再试。",
                    mention_author=False,
                )
                return
        # 加锁后重读再写：tv_granted 检查与落盘原子化，避免两位管理员
        # 同时 !tvdone 同一用户时重复记录；也不会覆盖并发的 drip/报名写入。
        async with self._state_lock:
            state = load_trial30_state()
            rec = state["claimed"].get(uid, {})
            already_tv = rec.get("tv_username") if rec.get("tv_granted") else None
            if already_tv is None:
                rec["tv_username"] = tv_username
                rec["tv_granted"] = True
                state["claimed"][uid] = rec
                save_trial30_state(state)
        if already_tv is not None:
            await ctx.reply(
                f"{member.mention} 的 TV 权限已标记过（`{already_tv}`）。",
                mention_author=False,
            )
            return
        logger.info("trial30: tvdone recorded tv=%s for %s", tv_username, uid)
        try:
            await member.send(TRIAL30_TVDONE_CONFIRM)
        except discord.Forbidden:
            logger.info("trial30: tvdone-confirm DM blocked for %s", uid)
        except Exception as exc:
            logger.warning("trial30: tvdone-confirm DM to %s failed: %s", uid, exc)
        await ctx.reply(
            f"✅ 已记录 {member.mention} 的 TV 用户名 `{tv_username}`，"
            "用户已收到开通通知。",
            mention_author=False,
        )

    @tvdone.error
    async def tvdone_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """!tvdone 参数错误的清晰提示。

        bot 全局没有 on_command_error：@成员 解析失败（输错/成员已退群）
        默认会被静默吞掉，用户得不到任何反馈。
        """
        if isinstance(error, commands.MemberNotFound):
            await ctx.reply(
                "找不到该成员：请检查 @ 是否正确（成员可能已退群）。\n"
                "用法：`!tvdone @成员 <TradingView用户名>`",
                mention_author=False,
            )
        elif isinstance(error, commands.CheckFailure):
            await ctx.reply("`!tvdone` 需要管理员权限。", mention_author=False)
        else:
            logger.warning("trial30: tvdone unexpected error: %r", error)

    def _member_has_trial_role(self, member: discord.Member) -> bool:
        """成员是否已持有「免费试用30天」组。"""
        return any(
            getattr(r, "name", "") == TRIAL30_ROLE_NAME
            for r in (getattr(member, "roles", None) or [])
        )

    def _has_paid_role(self, member: discord.Member) -> bool:
        """成员是否持有任一付费身份组（role id 命中，或 timed_roles 的付费组判定）。"""
        ids = {
            str(getattr(r, "id", "")) for r in (getattr(member, "roles", None) or [])
        }
        if ids & PAID_ROLE_IDS:
            return True
        try:
            return bool(is_paid_member(member))
        except Exception:
            return False

    # ── 到期回收 ────────────────────────────────────────────────────────

    async def _process_expiries(self) -> None:
        # 两阶段：先加锁收集到期名单（纯读盘），再逐个做网络 I/O，
        # 最后加锁重读合并落标记。锁不跨网络调用，避免长持有阻塞报名；
        # 重读合并避免 I/O 期间的并发写入（如新报名）被覆盖。
        async with self._state_lock:
            state = load_trial30_state()
            now = datetime.now(timezone.utc)
            opt_out = set(state.get("opt_out", []))
            todo: list[tuple[str, int | None, bool]] = []
            for uid, rec in state["claimed"].items():
                if rec.get("expired_done"):
                    continue
                exp = _parse_ts(rec.get("expires_at"))
                if not exp or exp > now:
                    continue
                todo.append((uid, rec.get("guild_id"), uid not in opt_out))
        for uid, guild_id, can_dm in todo:
            try:
                await self._expire_one(uid, guild_id=guild_id, can_dm=can_dm)
            except Exception as exc:  # 单条失败不影响其他人
                logger.warning("trial30: expire %s failed: %s", uid, exc)
        if not todo:
            return
        async with self._state_lock:
            state = load_trial30_state()
            for uid, _, _ in todo:
                rec = state["claimed"].get(uid)
                if rec is None or rec.get("expired_done"):
                    continue
                rec["expired_done"] = True
                # Day30 drip 即到期通知：记入 drip_sent，避免 drip 循环重复发送。
                drip_sent = rec.setdefault("drip_sent", [])
                if 30 not in drip_sent:
                    drip_sent.append(30)
            save_trial30_state(state)

    async def _expire_one(
        self, uid: str, guild_id: int | None = None, can_dm: bool = True
    ) -> None:
        """收回单个用户的试用组 + 挂过期标记 + 发 Day30 到期 DM。

        纯 Discord I/O，不碰 state 文件；expired_done/drip_sent 标记由
        _process_expiries 统一落盘。
        """
        user_id = int(uid)
        guild: discord.Guild | None = None
        if guild_id:
            guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            for g in self.bot.guilds:
                if g.get_member(user_id):
                    guild = g
                    break
        member = guild.get_member(user_id) if guild is not None else None
        if guild is not None and member is not None:
            trial_role = await _ensure_role(guild, TRIAL30_ROLE_NAME)
            if trial_role is not None and trial_role in member.roles:
                try:
                    await member.remove_roles(trial_role, reason="trial30 expired")
                    logger.info("trial30: revoked trial role from %s", uid)
                except discord.Forbidden:
                    logger.warning(
                        "trial30: missing MANAGE_ROLES — cannot revoke trial role from %s",
                        uid,
                    )
                except Exception as exc:
                    logger.warning(
                        "trial30: revoke trial role from %s failed: %s", uid, exc
                    )
            expired_role = await _ensure_role(guild, TRIAL30_EXPIRED_ROLE_NAME)
            if expired_role is not None and expired_role not in member.roles:
                try:
                    await member.add_roles(expired_role, reason="trial30 expired marker")
                except discord.Forbidden:
                    logger.warning(
                        "trial30: missing MANAGE_ROLES — cannot grant expired marker to %s",
                        uid,
                    )
                except Exception as exc:
                    logger.warning(
                        "trial30: grant expired marker to %s failed: %s", uid, exc
                    )
        else:
            logger.info(
                "trial30: member %s not found in any guild, skip role ops", uid
            )
        if can_dm:
            await _dm_user(self.bot, user_id, TRIAL30_DRIP[30])

    # ── 转化 drip ───────────────────────────────────────────────────────

    async def _process_drips(self) -> None:
        # 两阶段：先加锁收集到期 drip（纯读盘），再逐个发 DM，
        # 最后加锁重读合并落 sent 标记。锁不跨网络调用，重读合并避免
        # 发 DM 期间的并发写入（如新报名/STOP）被覆盖。
        async with self._state_lock:
            state = load_trial30_state()
            now = datetime.now(timezone.utc)
            opt_out = set(state.get("opt_out", []))
            todo: list[tuple[str, int]] = []
            for uid, rec in state["claimed"].items():
                if rec.get("expired_done"):
                    continue
                if uid in opt_out:
                    continue
                started = _parse_ts(rec.get("started_at"))
                if not started:
                    continue
                todo.extend(
                    (uid, day)
                    for day in due_drips(
                        started, now, rec.get("drip_sent"), drip_days=_DRIP_LOOP_DAYS
                    )
                )
        attempted: list[tuple[str, int]] = []
        for uid, day in todo:
            try:
                sent = await _dm_user(self.bot, int(uid), TRIAL30_DRIP[day])
            except Exception as exc:  # _dm_user 内部已吞掉异常，这里是双保险
                logger.warning(
                    "trial30: drip day %d to %s raised: %s", day, uid, exc
                )
                sent = False
            # 无论 DM 是否成功都记 sent：避免用户关闭私信时每小时空转重试。
            attempted.append((uid, day))
            if sent:
                logger.info("trial30: drip day %d sent to %s", day, uid)
            else:
                logger.info(
                    "trial30: drip day %d not delivered to %s (DM closed/failed), "
                    "marked sent to avoid retry spam",
                    day, uid,
                )
        if not attempted:
            return
        async with self._state_lock:
            state = load_trial30_state()
            for uid, day in attempted:
                rec = state["claimed"].get(uid)
                if rec is None:
                    continue
                drip_sent = rec.setdefault("drip_sent", [])
                if day not in drip_sent:
                    drip_sent.append(day)
            save_trial30_state(state)

    # ── 行为触发：promo DM ──────────────────────────────────────────────

    def _trial_join_view(self) -> discord.ui.View:
        """报名按钮 View（群发/行为触发 DM 共用）。"""
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label=TRIAL_JOIN_BUTTON_LABEL,
                style=discord.ButtonStyle.primary,
                custom_id=TRIAL_JOIN_BUTTON_ID,
            )
        )
        return view

    async def _maybe_send_promo(self, member: discord.Member, source: str) -> None:
        """符合试用资格且未领过、未发过 promo、未退订 → 发一次带 ✅ 按钮的 promo DM。

        检查→发送→落盘全程加锁：join/首条消息/reaction 三个触发器并发时，
        同一用户只会收到一次 promo DM。
        """
        if not TRIAL30_ENABLED:
            return
        if not campaign_active():
            return  # 活动过期后不再发新 promo
        if member.bot:
            return
        async with self._state_lock:
            state = load_trial30_state()
            uid = str(member.id)
            ok, reason = promo_gate(
                uid,
                has_paid_role=self._has_paid_role(member),
                already_claimed=uid in state["claimed"],
                account_created_at=getattr(member, "created_at", None),
                state=state,
            )
            if not ok:
                return
            text = TRIAL30_PROMO_TEMPLATE.format(name=member.display_name)
            user = self.bot.get_user(member.id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(member.id)
                except Exception as exc:
                    logger.info("trial30: fetch_user %s failed: %s", member.id, exc)
                    return
            try:
                await user.send(text, view=self._trial_join_view())
                sent = True
            except discord.Forbidden:
                sent = False  # 用户关闭私信，静默跳过
            except Exception as exc:
                logger.warning("trial30: promo DM to %s failed: %s", member.id, exc)
                sent = False
            if sent:
                state["claimed"].setdefault(uid, {})["promo_dm_sent"] = True
                save_trial30_state(state)
                logger.info("trial30: promo DM sent to %s (source=%s)", uid, source)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not TRIAL30_ENABLED or member.bot:
            return
        await self._maybe_send_promo(member, source="join")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # STOP 退订：纯 DM。TRIAL30_ENABLED=False 时也生效。
        if message.guild is None:
            if not message.author.bot and is_stop_message(message.content):
                await self._handle_stop(message)
            return
        # 群消息行为触发：该用户第一条群消息（持久化 seen 集合）。
        if not TRIAL30_ENABLED:
            return
        if message.author.bot:
            return
        content = (message.content or "").strip()
        if content.startswith("!"):  # 跳过命令消息（如 !试用 本身）
            return
        author = message.author
        if not isinstance(author, discord.Member):
            return
        state = load_trial30_state()
        uid = str(author.id)
        seen = set(state.get("seen_first_msg", []))
        if uid in seen:
            return
        seen.add(uid)
        state["seen_first_msg"] = sorted(seen)
        save_trial30_state(state)
        await self._maybe_send_promo(author, source="first_message")

    @commands.Cog.listener()
    async def on_reaction_add(
        self, reaction: discord.Reaction, user: discord.abc.User
    ) -> None:
        if not TRIAL30_ENABLED or user.bot:
            return
        member = user if isinstance(user, discord.Member) else None
        if member is None:
            guild = getattr(reaction.message, "guild", None)
            if guild is not None:
                member = guild.get_member(user.id)
        if member is None:
            return
        await self._maybe_send_promo(member, source="reaction")

    # ── STOP 退订 ───────────────────────────────────────────────────────

    async def _handle_stop(self, message: discord.Message) -> None:
        uid = str(message.author.id)
        async with self._state_lock:
            state = load_trial30_state()
            opt_out = set(state.get("opt_out", []))
            if uid not in opt_out:
                opt_out.add(uid)
                state["opt_out"] = sorted(opt_out)
                save_trial30_state(state)
                _sync_opt_out_to_broadcast(uid)
                logger.info("trial30: user %s opted out (STOP)", uid)
        try:
            await message.author.send("已退订，不再打扰 🙏")
        except discord.Forbidden:
            pass
        except Exception as exc:
            logger.warning("trial30: opt-out confirm DM to %s failed: %s", uid, exc)
