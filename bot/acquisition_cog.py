"""Acquisition cog — welcome drip loop, invite tracking, persistent CTA view."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from bot.acquisition import (
    AcquisitionCtaView,
    diff_invite_attribution,
    due_drip_jobs,
    load_invite_code_snapshot,
    mark_drip_sent,
    record_funnel,
    record_invite_join,
    save_invite_code_snapshot,
    send_drip_job,
    should_grant_invite_reward,
    snapshot_invite_codes,
)
from bot.config import INVITE_REWARD_ROLE_ID, INVITE_TRACKING_ENABLED

logger = logging.getLogger(__name__)


class AcquisitionCog(commands.Cog):
    """Background drip sender + invite-use attribution."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.bot.add_view(AcquisitionCtaView())
        if INVITE_TRACKING_ENABLED:
            await self._refresh_invite_snapshot()
        if not self._drip_loop.is_running():
            self._drip_loop.start()

    async def cog_unload(self) -> None:
        self._drip_loop.cancel()

    @tasks.loop(seconds=60)
    async def _drip_loop(self) -> None:
        for job in due_drip_jobs():
            ok = await send_drip_job(self.bot, job)
            if ok:
                mark_drip_sent(job["id"])

    @_drip_loop.before_loop
    async def _before_drip(self) -> None:
        await self.bot.wait_until_ready()

    async def _refresh_invite_snapshot(self) -> None:
        codes: dict[str, dict] = {}
        for guild in self.bot.guilds:
            try:
                invites = await guild.invites()
            except discord.Forbidden:
                logger.info("Invite tracking: missing permission to list invites in %s", guild.id)
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
        if not INVITE_TRACKING_ENABLED:
            return

        previous = load_invite_code_snapshot()
        try:
            invites = await member.guild.invites()
        except discord.Forbidden:
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

        if should_grant_invite_reward(count):
            role = member.guild.get_role(INVITE_REWARD_ROLE_ID)
            inviter = member.guild.get_member(inviter_id)
            if role and inviter and role not in inviter.roles:
                try:
                    await inviter.add_roles(role, reason=f"Invite reward ({count} joins)")
                except Exception as exc:
                    logger.warning("Failed to grant invite reward role: %s", exc)
