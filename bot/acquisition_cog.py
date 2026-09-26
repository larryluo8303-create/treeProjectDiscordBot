"""Acquisition cog — welcome drip loop, invite tracking, timed-role rewards."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from bot.acquisition import (
    AcquisitionCtaView,
    cancel_drip_for_user,
    diff_invite_attribution,
    due_drip_jobs,
    is_month_settled,
    load_invite_code_snapshot,
    mark_drip_sent,
    mark_month_settled,
    monthly_top_inviters,
    record_funnel,
    record_invite_join,
    save_invite_code_snapshot,
    send_drip_job,
    snapshot_invite_codes,
)
from bot.config import (
    INVITE_ETF_REWARD_ROLE_ID,
    INVITE_FULL_REWARD_ROLE_ID,
    INVITE_REWARD_DAYS,
    INVITE_TOPN_COUNT,
    INVITE_TRACKING_ENABLED,
    TRIAL_GRANT_DAYS,
    TRIAL_ROLE_NAME,
)
from bot.timed_roles import (
    _parse_ts,
    cancel_grants_for_user,
    ensure_trial_overwrites,
    ensure_trial_role,
    grant_timed_role,
    has_active_grant,
    is_paid_member,
    last_grant,
    revoke_due_timed_roles,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# A new ETF invite reward is granted at most once per 30 days per inviter.
_ETF_REWARD_COOLDOWN_SECONDS = 30 * 86400


class AcquisitionCog(commands.Cog):
    """Background drip sender + invite attribution + timed reward roles."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.bot.add_view(AcquisitionCtaView())
        await self._ensure_trial_access()
        self._startup_permission_check()
        if INVITE_TRACKING_ENABLED:
            await self._refresh_invite_snapshot()
        for loop in (self._drip_loop, self._timed_roles_loop, self._settlement_loop):
            if not loop.is_running():
                loop.start()

    async def cog_unload(self) -> None:
        self._drip_loop.cancel()
        self._timed_roles_loop.cancel()
        self._settlement_loop.cancel()

    # ── loops ──────────────────────────────────────────────────────────────

    @tasks.loop(seconds=60)
    async def _drip_loop(self) -> None:
        for job in due_drip_jobs():
            ok = await send_drip_job(self.bot, job)
            if ok:
                mark_drip_sent(job["id"])

    @_drip_loop.before_loop
    async def _before_drip(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=5)
    async def _timed_roles_loop(self) -> None:
        try:
            closed = await revoke_due_timed_roles(self.bot)
            if closed:
                logger.info("timed_roles: revoked %d expired grant(s)", closed)
        except Exception as exc:
            logger.warning("timed_roles loop failed: %s", exc)

    @_timed_roles_loop.before_loop
    async def _before_timed_roles(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def _settlement_loop(self) -> None:
        try:
            await self._maybe_monthly_settlement()
        except Exception as exc:
            logger.warning("settlement loop failed: %s", exc)

    @_settlement_loop.before_loop
    async def _before_settlement(self) -> None:
        await self.bot.wait_until_ready()

    # ── trial access (NOT gated by INVITE_TRACKING_ENABLED) ─────────────────

    async def _ensure_trial_access(self) -> None:
        for guild in self.bot.guilds:
            try:
                role = await ensure_trial_role(guild)
            except Exception as exc:
                logger.warning("trial setup failed for guild %s: %s", guild.id, exc)
                continue
            if role is None:
                continue
            try:
                await ensure_trial_overwrites(guild, role)
            except Exception as exc:
                logger.warning("trial overwrites failed for guild %s: %s", guild.id, exc)

    def _startup_permission_check(self) -> None:
        """Log which growth features degrade without privileged perms."""
        for guild in self.bot.guilds:
            me = guild.me
            if me is None:
                continue
            perms = me.guild_permissions
            missing: list[str] = []
            if not perms.manage_guild:
                missing.append("MANAGE_GUILD（邀请列表追踪将不可用）")
            if not perms.manage_roles:
                missing.append("MANAGE_ROLES（身份组发放/回收/体验组将不可用）")
            if not perms.create_instant_invite:
                missing.append("CREATE_INSTANT_INVITE（/invite 专属链接将不可用）")
            if missing:
                logger.warning(
                    "Startup check guild %s: bot 缺少权限：%s —— 对应功能降级（只记日志，不崩）",
                    guild.id, "；".join(missing),
                )
            else:
                logger.info("Startup check guild %s: 增长所需权限完整", guild.id)

    async def _grant_trial_access(self, member: discord.Member) -> None:
        """Give a new non-paid member the 15-day read-only trial role."""
        if is_paid_member(member):
            return
        guild = member.guild
        role = discord.utils.get(guild.roles, name=TRIAL_ROLE_NAME)
        if role is None:
            role = await ensure_trial_role(guild)
        if role is None:
            return
        await grant_timed_role(
            self.bot, member.id, guild.id, role.id, TRIAL_GRANT_DAYS, "trial"
        )

    # ── invite tracking ────────────────────────────────────────────────────

    async def _refresh_invite_snapshot(self) -> None:
        codes: dict[str, dict] = {}
        for guild in self.bot.guilds:
            try:
                invites = await guild.invites()
            except discord.Forbidden:
                logger.info("Invite tracking: missing MANAGE_GUILD to list invites in %s", guild.id)
                continue
            except Exception as exc:
                logger.warning("Invite snapshot failed for guild %s: %s", guild.id, exc)
                continue
            codes.update(snapshot_invite_codes(invites))
        save_invite_code_snapshot(codes)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if INVITE_TRACKING_ENABLED:
            await self._refresh_invite_snapshot()

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if INVITE_TRACKING_ENABLED:
            await self._refresh_invite_snapshot()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        record_funnel("joins")
        # Trial access + welcome DM are independent of invite tracking.
        await self._grant_trial_access(member)
        if not INVITE_TRACKING_ENABLED:
            return

        previous = load_invite_code_snapshot()
        try:
            invites = await member.guild.invites()
        except discord.Forbidden:
            logger.info("Invite attribution: missing MANAGE_GUILD in %s", member.guild.id)
            return
        except Exception as exc:
            logger.warning("Invite list on join failed: %s", exc)
            return

        current = snapshot_invite_codes(invites)
        hit = diff_invite_attribution(previous, current)
        save_invite_code_snapshot(current)
        if not hit:
            return
        code, inviter_id = hit
        if not inviter_id or inviter_id == member.id:
            return
        count = record_invite_join(code, inviter_id, member.id, member.guild.id)
        logger.info(
            "Invite attribution: %s joined via %s (inviter=%s, total=%d)",
            member.id, code, inviter_id, count,
        )
        await self._maybe_grant_invite_etf_reward(member.guild, inviter_id, count)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        n_drip = cancel_drip_for_user(member.id)
        n_grants = cancel_grants_for_user(member.id)
        if n_drip or n_grants:
            logger.info(
                "Member %s left: cancelled %d drip job(s), %d timed grant(s)",
                member.id, n_drip, n_grants,
            )

    # ── per-invite ETF reward ──────────────────────────────────────────────

    async def _maybe_grant_invite_etf_reward(
        self, guild: discord.Guild, inviter_id: int, count: int
    ) -> None:
        """First successful invite earns the ETF reward role for INVITE_REWARD_DAYS.

        Re-grants are allowed only when the previous grant expired more than
        30 days ago.
        """
        if count < 1 or not INVITE_ETF_REWARD_ROLE_ID:
            return
        if has_active_grant(inviter_id, INVITE_ETF_REWARD_ROLE_ID):
            return
        prev = last_grant(inviter_id, INVITE_ETF_REWARD_ROLE_ID, reason="invite_etf")
        if prev:
            exp = _parse_ts(prev.get("expires_at"))
            if exp and (datetime.now(timezone.utc) - exp).total_seconds() < _ETF_REWARD_COOLDOWN_SECONDS:
                return
        ok = await grant_timed_role(
            self.bot,
            inviter_id,
            guild.id,
            INVITE_ETF_REWARD_ROLE_ID,
            INVITE_REWARD_DAYS,
            "invite_etf",
        )
        if not ok:
            return
        user = self.bot.get_user(inviter_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(inviter_id)
            except Exception:
                return
        embed = discord.Embed(
            title="🎉 邀请奖励到账！",
            description=(
                f"你已成功邀请 **{count}** 位朋友加入社群，"
                f"获得 **ETF 版会员**（懒人ETF🌲）**{INVITE_REWARD_DAYS} 天**！\n\n"
                f"继续邀请，月度 Top{INVITE_TOPN_COUNT} 还可获得 **full 版会员 1 个月**。"
            ),
            color=discord.Color.gold(),
        )
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            logger.info("Invite reward DM blocked for user %s", inviter_id)
        except Exception as exc:
            logger.warning("Invite reward DM failed for %s: %s", inviter_id, exc)

    # ── monthly TopN settlement ────────────────────────────────────────────

    async def _maybe_monthly_settlement(self) -> None:
        month_key = datetime.now(_ET).strftime("%Y-%m")
        if is_month_settled(month_key):
            return
        top = monthly_top_inviters(INVITE_TOPN_COUNT)
        if not top:
            mark_month_settled(month_key)
            return
        for guild in self.bot.guilds:
            role = guild.get_role(INVITE_FULL_REWARD_ROLE_ID)
            if role is None:
                logger.warning(
                    "settlement: full-reward role %s not found in guild %s",
                    INVITE_FULL_REWARD_ROLE_ID, guild.id,
                )
                continue
            for inviter_id, count in top:
                member = guild.get_member(inviter_id)
                if member is None:
                    try:
                        member = await guild.fetch_member(inviter_id)
                    except Exception:
                        member = None
                if member is None:
                    continue
                if is_paid_member(member):
                    logger.info("settlement: skip %s — paid cohort member", inviter_id)
                    continue
                ok = await grant_timed_role(
                    self.bot,
                    inviter_id,
                    guild.id,
                    INVITE_FULL_REWARD_ROLE_ID,
                    INVITE_REWARD_DAYS,
                    "invite_monthly_top",
                )
                if not ok:
                    continue
                try:
                    await member.send(
                        "🏆 **月度邀请 Top 奖励**\n"
                        f"你在近 30 天成功邀请 **{count}** 人，位列前 {INVITE_TOPN_COUNT}，"
                        f"获得 **full 版会员**（懒人🌴）**{INVITE_REWARD_DAYS} 天**！感谢你的推广 🙏"
                    )
                except Exception:
                    pass
                logger.info(
                    "settlement: granted full reward to %s (count=%d)", inviter_id, count
                )
        mark_month_settled(month_key)
