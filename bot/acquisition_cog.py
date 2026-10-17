"""Acquisition cog — welcome drip loop, invite tracking, timed-role rewards."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from bot.acquisition import (
    AcquisitionCtaView,
    ambassador_due_tiers,
    ambassador_role_id,
    ambassador_role_label,
    ambassador_role_name,
    ambassador_tier_reason,
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
    verified_invite_count,
)
from bot.config import (
    INVITE_ETF_MIN_COUNT,
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
    supersede_grants,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# A new ETF invite reward is granted at most once per 30 days per inviter.
_ETF_REWARD_COOLDOWN_SECONDS = 30 * 86400

# Missed-join backfill (2026-09-28): Discord never resends GUILD_MEMBER_ADD for
# joins that happened while the gateway was down, so after every (re)connect we
# sweep members who joined recently and grant the trial role to anyone whose
# on_member_join was lost in transit.
_MISSED_JOIN_LOOKBACK_SECONDS = 24 * 3600
_MISSED_JOIN_BACKFILL_COOLDOWN_SECONDS = 15 * 60


class AcquisitionCog(commands.Cog):
    """Background drip sender + invite attribution + timed reward roles."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._last_backfill_at = 0.0

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.bot.add_view(AcquisitionCtaView())
        await self._ensure_trial_access()
        try:
            await self._backfill_missed_joins("ready")
        except Exception as exc:
            logger.warning("missed-join backfill on ready failed: %s", exc)
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
        """Give every new member the 15-day read-only trial role."""
        guild = member.guild
        role = discord.utils.get(guild.roles, name=TRIAL_ROLE_NAME)
        if role is None:
            role = await ensure_trial_role(guild)
        if role is None:
            return
        await grant_timed_role(
            self.bot, member.id, guild.id, role.id, TRIAL_GRANT_DAYS, "trial"
        )

    async def _backfill_missed_joins(self, reason: str) -> None:
        """Grant the trial role to recent joiners whose join event was lost.

        Discord does not resend GUILD_MEMBER_ADD for joins that happened while
        the gateway was down, so after every (re)connect we sweep members who
        joined within the lookback window. Every newcomer gets the trial role,
        no exceptions: members that already hold the trial role or have an
        active grant are left alone (idempotent).
        """
        now = time.monotonic()
        if now - self._last_backfill_at < _MISSED_JOIN_BACKFILL_COOLDOWN_SECONDS:
            return
        self._last_backfill_at = now
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=_MISSED_JOIN_LOOKBACK_SECONDS
        )
        checked = granted = 0
        for guild in self.bot.guilds:
            role = discord.utils.get(guild.roles, name=TRIAL_ROLE_NAME)
            if role is None:
                role = await ensure_trial_role(guild)
            if role is None:
                continue
            try:
                members = [m async for m in guild.fetch_members(limit=None)]
            except Exception as exc:
                logger.warning(
                    "missed-join backfill: fetch_members failed for guild %s: %s",
                    guild.id,
                    exc,
                )
                continue
            for member in members:
                if member.bot:
                    continue
                joined_at = member.joined_at
                if joined_at is None or joined_at < cutoff:
                    continue
                checked += 1
                if role in member.roles:
                    continue
                if has_active_grant(member.id, role.id):
                    continue
                ok = await grant_timed_role(
                    self.bot,
                    member.id,
                    guild.id,
                    role.id,
                    TRIAL_GRANT_DAYS,
                    "trial-backfill",
                )
                if ok:
                    granted += 1
        if checked or granted:
            logger.info(
                "missed-join backfill (%s): checked %d recent joiner(s), "
                "granted trial to %d",
                reason,
                checked,
                granted,
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
    async def on_resumed(self) -> None:
        try:
            await self._backfill_missed_joins("resumed")
        except Exception as exc:
            logger.warning("missed-join backfill on resume failed: %s", exc)

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
        await self._maybe_grant_ambassador_rewards(member.guild, inviter_id)

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
        """Reaching INVITE_ETF_MIN_COUNT successful invites earns the ETF reward
        role for INVITE_REWARD_DAYS.

        Re-grants are allowed only when the previous grant expired more than
        30 days ago.
        """
        if count < INVITE_ETF_MIN_COUNT or not INVITE_ETF_REWARD_ROLE_ID:
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

    # ── ambassador tiered rewards ────────────────────────────────────────

    async def _maybe_grant_ambassador_rewards(
        self, guild: discord.Guild, inviter_id: int
    ) -> None:
        """Grant ambassador tiers whose marginal verified-invite count qualifies.

        Verified count excludes joiners who already left the guild (anti-fraud).
        A higher tier for the same role supersedes earlier grants so the revoke
        loop never yanks the role at an old grant's expiry.
        """
        try:
            verified = await verified_invite_count(guild, inviter_id)
        except Exception as exc:
            logger.warning("ambassador: verified count failed for %s: %s", inviter_id, exc)
            return
        due = ambassador_due_tiers(inviter_id, verified)
        for tier in due:
            role_id = ambassador_role_id(tier)
            if not role_id:
                continue
            reason = ambassador_tier_reason(tier)
            # A longer/higher grant wins: retire older records of the same role
            # (record-only; the role itself stays on the user).
            supersede_grants(inviter_id, role_id, note=f"superseded by {reason}")
            ok = await grant_timed_role(
                self.bot,
                inviter_id,
                guild.id,
                role_id,
                int(tier["days"]),
                reason,
                meta={"count_at_grant": verified},
            )
            if not ok:
                continue
            logger.info(
                "ambassador: granted tier %s (%dd, role %s) to %s (verified=%d)",
                tier["invites"], tier["days"], role_id, inviter_id, verified,
            )
            await self._dm_ambassador_reward(inviter_id, tier, verified)

    async def _dm_ambassador_reward(
        self, inviter_id: int, tier: dict, verified: int
    ) -> None:
        from bot.acquisition import (
            ambassador_progress,
            next_ambassador_tier_gap,
        )

        role_label = ambassador_role_label(tier)
        role_name = ambassador_role_name(tier)
        gap = next_ambassador_tier_gap(inviter_id, verified)
        if gap and gap[1] > 0:
            next_line = f"\n\n继续加油：下一档 **{gap[0]} 人**，还差 **{gap[1]}** 人。"
        elif gap and gap[1] == 0:
            next_line = "\n\n🎊 你已达成最高档，继续保持！"
        else:
            next_line = ""
        embed = discord.Embed(
            title="🏆 推广大使奖励到账！",
            description=(
                f"你累计成功邀请 **{verified}** 位朋友（已核验仍在群内），"
                f"达成推广大使 **{tier['invites']} 人**档，"
                f"获得 **{role_label}**（{role_name}）**{tier['days']} 天**！{next_line}"
            ),
            color=discord.Color.gold(),
        )
        user = self.bot.get_user(inviter_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(inviter_id)
            except Exception:
                return
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            logger.info("ambassador reward DM blocked for user %s", inviter_id)
        except Exception as exc:
            logger.warning("ambassador reward DM failed for %s: %s", inviter_id, exc)

    # ── monthly TopN settlement ────────────────────────────────────────────

    async def _maybe_monthly_settlement(self) -> None:
        month_key = datetime.now(_ET).strftime("%Y-%m")
        if is_month_settled(month_key):
            return
        top = monthly_top_inviters(INVITE_TOPN_COUNT)
        if not top:
            mark_month_settled(month_key)
            return
        failed = False
        for guild in self.bot.guilds:
            role = guild.get_role(INVITE_FULL_REWARD_ROLE_ID)
            if role is None:
                logger.warning(
                    "settlement: full-reward role %s not found in guild %s",
                    INVITE_FULL_REWARD_ROLE_ID, guild.id,
                )
                failed = True
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
                if has_active_grant(inviter_id, INVITE_FULL_REWARD_ROLE_ID):
                    continue  # already rewarded (e.g. retried settlement)
                ok = await grant_timed_role(
                    self.bot,
                    inviter_id,
                    guild.id,
                    INVITE_FULL_REWARD_ROLE_ID,
                    INVITE_REWARD_DAYS,
                    "invite_monthly_top",
                )
                if not ok:
                    failed = True
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
        if failed:
            # Do NOT mark settled — the 24h loop will retry tomorrow. Winners
            # that already got the role are skipped via has_active_grant above.
            logger.warning(
                "settlement: some grants failed for %s, will retry on next loop",
                month_key,
            )
            return
        mark_month_settled(month_key)
