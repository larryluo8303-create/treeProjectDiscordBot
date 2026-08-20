"""Opt-in promotional DMs for allowlisted notify roles only.

Members must self-join a role in ``PROMO_NOTIFY_ROLE_IDS``. Existing
ops/interest tags must not be used as DM targets.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord

from bot.config import (
    PROMO_DM_DELAY_SECONDS,
    PROMO_DM_MAX_RECIPIENTS,
    PROMO_NOTIFY_ROLE_IDS,
    SIGNAL_PRODUCT_URL,
)

logger = logging.getLogger(__name__)

_broadcast_lock = asyncio.Lock()
_MAX_PANEL_ROLES = 5


def is_allowed_notify_role(role_id: int) -> bool:
    """Return True if *role_id* is in the voluntary notify-role allowlist."""
    return bool(role_id) and role_id in PROMO_NOTIFY_ROLE_IDS


def notify_role_error(role: discord.Role | None, *, required: bool) -> str | None:
    """User-facing error if a role cannot be used for promo DMs."""
    if not PROMO_NOTIFY_ROLE_IDS:
        return (
            "未配置 `PROMO_NOTIFY_ROLE_IDS`。请先创建自愿领取的「活动通知」身份组并写入 `.env`。"
        )
    if role is None:
        if required:
            return "请选择白名单里的通知身份组。"
        return None
    if not is_allowed_notify_role(role.id):
        return (
            "该身份组不在促销私信白名单中。"
            "不能用运营/兴趣标签群发私信，请让成员自愿领取通知身份组。"
        )
    return None


def default_notify_role_id() -> int | None:
    return PROMO_NOTIFY_ROLE_IDS[0] if PROMO_NOTIFY_ROLE_IDS else None


def reject_if_over_limit(
    count: int,
    max_recipients: int | None = None,
) -> dict[str, Any] | None:
    """Return an error result dict if *count* exceeds the safety cap."""
    cap = PROMO_DM_MAX_RECIPIENTS if max_recipients is None else max_recipients
    if count > cap:
        return {
            "sent": 0,
            "blocked": 0,
            "failed": 0,
            "skipped": 0,
            "error": "over_limit",
            "count": count,
            "max": cap,
        }
    return None


async def collect_role_members(
    guild: discord.Guild,
    role: discord.Role,
) -> list[discord.Member]:
    """Humans in *guild* who currently have *role* (bots excluded)."""
    if not getattr(guild, "chunked", True):
        chunk = getattr(guild, "chunk", None)
        if callable(chunk):
            await chunk()
    return [m for m in role.members if not getattr(m, "bot", False)]


def build_promo_dm_embed(title: str, description: str, url: str = "") -> discord.Embed:
    embed = discord.Embed(
        title=f"🌳 {title}",
        description=description,
        color=discord.Color.gold(),
    )
    link = url or SIGNAL_PRODUCT_URL
    if link:
        embed.add_field(name="🔗 链接", value=f"[点击查看]({link})", inline=False)
    embed.set_footer(text="不想再收到活动私信，点下面的「取消订阅」。")
    return embed


def build_notify_panel_embed(guild: discord.Guild | None = None) -> discord.Embed:
    names: list[str] = []
    if guild is not None:
        for rid in PROMO_NOTIFY_ROLE_IDS[:_MAX_PANEL_ROLES]:
            role = guild.get_role(rid)
            if role:
                names.append(role.mention)
    role_line = "、".join(names) if names else "活动通知"
    return discord.Embed(
        title="活动私信通知",
        description=(
            "想在优惠/活动时收到**私信**，请点下面的「领取通知」。\n"
            "随时可取消。不会用你现有的运营分组来发私信。\n\n"
            f"可订阅：{role_line}"
        ),
        color=discord.Color.green(),
    )


def format_broadcast_result(result: dict[str, Any]) -> str:
    err = result.get("error")
    if err == "role_not_allowed":
        return "该身份组不在促销私信白名单（PROMO_NOTIFY_ROLE_IDS）中。"
    if err == "over_limit":
        return (
            f"订阅人数 {result.get('count', 0)} 超过上限 "
            f"{result.get('max', PROMO_DM_MAX_RECIPIENTS)}。"
            "请拆批发送，或提高 `PROMO_DM_MAX_RECIPIENTS`。"
        )
    if err == "busy":
        return "已有一次促销私信正在发送，请稍后再试。"
    if err == "no_members":
        return "该通知身份组目前没有成员。请先在公告频道发订阅面板，让成员自愿领取。"
    return (
        "促销私信发送完成。\n"
        f"成功：{result.get('sent', 0)}　"
        f"关闭私信：{result.get('blocked', 0)}　"
        f"失败：{result.get('failed', 0)}"
    )


def parse_dm_unsub_custom_id(custom_id: str) -> tuple[int, int] | None:
    """Parse ``promo_dm:unsub:{guild_id}:{role_id}``."""
    parts = custom_id.split(":")
    if len(parts) != 4 or parts[0] != "promo_dm" or parts[1] != "unsub":
        return None
    if not parts[2].isdigit() or not parts[3].isdigit():
        return None
    return int(parts[2]), int(parts[3])


def parse_notify_toggle_custom_id(custom_id: str) -> tuple[bool, int, int | None] | None:
    """Parse ``promo_notify:{sub|unsub}:{role_id}`` or ``...:{role_id}:{guild_id}``."""
    parts = custom_id.split(":")
    if parts and parts[0] != "promo_notify":
        return None
    if len(parts) not in (3, 4):
        return None
    if parts[1] not in ("sub", "unsub") or not parts[2].isdigit():
        return None
    guild_id: int | None = None
    if len(parts) == 4:
        if not parts[3].isdigit():
            return None
        guild_id = int(parts[3])
    return parts[1] == "sub", int(parts[2]), guild_id


async def apply_notify_role(
    member: discord.Member,
    role: discord.Role,
    subscribe: bool,
) -> str:
    """Add or remove a notify role. Returns a status key."""
    if not is_allowed_notify_role(role.id):
        return "not_allowed"
    try:
        if subscribe:
            if role in member.roles:
                return "already"
            await member.add_roles(role, reason="Promo notify opt-in")
            return "subscribed"
        if role not in member.roles:
            return "not_subscribed"
        await member.remove_roles(role, reason="Promo notify opt-out")
        return "unsubscribed"
    except discord.Forbidden:
        logger.warning("Cannot change notify role %s for %s — missing permission", role.id, member.id)
        return "forbidden"
    except Exception as exc:
        logger.warning("Notify role toggle failed for %s: %s", member.id, exc)
        return "error"


def status_message(status: str, role: discord.Role | None = None) -> str:
    mention = role.mention if role is not None else "通知身份组"
    return {
        "subscribed": f"已订阅 {mention}，之后的活动私信会发给你。",
        "already": f"你已经订阅了 {mention}。",
        "unsubscribed": f"已取消 {mention}，不会再收到活动私信。现有运营标签不会改动。",
        "not_subscribed": f"你尚未订阅 {mention}。",
        "not_allowed": "该身份组不是自愿通知身份组，无法用于活动私信。",
        "forbidden": "Bot 无法修改该身份组。请确认 Bot 有「管理身份组」权限，且 Bot 身份组排在通知身份组上面。",
        "error": "操作失败，请稍后再试。",
        "not_in_guild": "请在服务器里操作，或先加入服务器。",
    }.get(status, "操作失败，请稍后再试。")


async def handle_notify_toggle(
    interaction: discord.Interaction,
    role_id: int,
    subscribe: bool,
    guild_id: int | None = None,
) -> None:
    if interaction.response.is_done():
        return
    guild = interaction.guild
    if guild is None and guild_id:
        guild = interaction.client.get_guild(guild_id)
    if guild is None:
        await interaction.response.send_message(status_message("not_in_guild"), ephemeral=True)
        return
    role = guild.get_role(role_id)
    if role is None or not is_allowed_notify_role(role_id):
        await interaction.response.send_message(status_message("not_allowed"), ephemeral=True)
        return
    member: discord.Member | None = None
    if isinstance(interaction.user, discord.Member) and interaction.user.guild.id == guild.id:
        member = interaction.user
    if member is None:
        member = guild.get_member(interaction.user.id)
    if member is None:
        try:
            member = await guild.fetch_member(interaction.user.id)
        except discord.NotFound:
            await interaction.response.send_message(status_message("not_in_guild"), ephemeral=True)
            return
        except Exception as exc:
            logger.warning("fetch_member failed during notify toggle: %s", exc)
            await interaction.response.send_message(status_message("error"), ephemeral=True)
            return
    status = await apply_notify_role(member, role, subscribe)
    await interaction.response.send_message(status_message(status, role), ephemeral=True)


async def handle_dm_unsub(interaction: discord.Interaction, custom_id: str) -> None:
    parsed = parse_dm_unsub_custom_id(custom_id)
    if parsed is None:
        return
    guild_id, role_id = parsed
    if interaction.response.is_done():
        return
    bot = interaction.client
    guild = bot.get_guild(guild_id)
    if guild is None:
        await interaction.response.send_message("找不到对应的服务器。", ephemeral=True)
        return
    role = guild.get_role(role_id)
    if role is None or not is_allowed_notify_role(role_id):
        await interaction.response.send_message(status_message("not_allowed"), ephemeral=True)
        return
    member = guild.get_member(interaction.user.id)
    if member is None:
        try:
            member = await guild.fetch_member(interaction.user.id)
        except discord.NotFound:
            await interaction.response.send_message(status_message("not_in_guild"), ephemeral=True)
            return
        except Exception as exc:
            logger.warning("fetch_member failed during DM unsub: %s", exc)
            await interaction.response.send_message(status_message("error"), ephemeral=True)
            return
    status = await apply_notify_role(member, role, subscribe=False)
    await interaction.response.send_message(status_message(status, role), ephemeral=True)


class NotifyToggleButton(discord.ui.Button):
    def __init__(
        self,
        role_id: int,
        subscribe: bool,
        row: int,
        label: str | None = None,
        guild_id: int | None = None,
    ) -> None:
        if label is None:
            label = "领取通知" if subscribe else "取消订阅"
        custom_id = f"promo_notify:{'sub' if subscribe else 'unsub'}:{role_id}"
        if guild_id:
            custom_id = f"{custom_id}:{guild_id}"
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.success if subscribe else discord.ButtonStyle.secondary,
            custom_id=custom_id,
            row=row,
        )
        self.role_id = role_id
        self.subscribe = subscribe
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await handle_notify_toggle(
            interaction, self.role_id, self.subscribe, self.guild_id,
        )


def attach_welcome_notify_buttons(
    view: discord.ui.View,
    guild: discord.Guild,
    row: int = 1,
) -> None:
    """Add one 领取通知 / 取消订阅 pair for the default notify role (DM-safe custom_ids)."""
    role_id = default_notify_role_id()
    if not role_id:
        return
    view.add_item(NotifyToggleButton(role_id, True, row, "领取通知", guild_id=guild.id))
    view.add_item(NotifyToggleButton(role_id, False, row, "取消订阅", guild_id=guild.id))


class PromoNotifyView(discord.ui.View):
    """Persistent subscribe/unsubscribe panel for allowlisted notify roles."""

    def __init__(self, guild: discord.Guild | None = None) -> None:
        super().__init__(timeout=None)
        role_ids = PROMO_NOTIFY_ROLE_IDS[:_MAX_PANEL_ROLES]
        multi = len(role_ids) > 1
        for i, rid in enumerate(role_ids):
            role_name = ""
            if guild is not None:
                role = guild.get_role(rid)
                role_name = role.name if role else ""
            sub_label = f"领取 {role_name}" if multi and role_name else "领取通知"
            unsub_label = f"取消 {role_name}" if multi and role_name else "取消订阅"
            self.add_item(NotifyToggleButton(rid, True, i, sub_label))
            self.add_item(NotifyToggleButton(rid, False, i, unsub_label))


class PromoDmUnsubView(discord.ui.View):
    """Button attached to promo DMs. Handled via ``on_interaction`` (dynamic guild id)."""

    def __init__(self, guild_id: int, role_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="取消订阅",
                style=discord.ButtonStyle.secondary,
                custom_id=f"promo_dm:unsub:{guild_id}:{role_id}",
            )
        )


class RoleDmConfirmView(discord.ui.View):
    """Ephemeral Owner confirm before a role DM blast."""

    def __init__(
        self,
        *,
        guild_id: int,
        role_id: int,
        title: str,
        description: str,
        url: str,
        owner_id: int,
    ) -> None:
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.role_id = role_id
        self.title = title
        self.description = description
        self.url = url
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("只有发起人可以确认。", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="确认发送", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(content="正在发送促销私信…", view=None)
        self.stop()
        asyncio.create_task(self._run(interaction))

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(content="已取消发送。", view=None)
        self.stop()

    async def _run(self, interaction: discord.Interaction) -> None:
        bot = interaction.client
        guild = bot.get_guild(self.guild_id)
        if guild is None:
            await interaction.followup.send("找不到服务器。", ephemeral=True)
            return
        role = guild.get_role(self.role_id)
        if role is None:
            await interaction.followup.send("找不到通知身份组。", ephemeral=True)
            return
        embed = build_promo_dm_embed(self.title, self.description, self.url)
        result = await broadcast_role_dm(guild, role, embed)
        await interaction.followup.send(format_broadcast_result(result), ephemeral=True)


async def broadcast_role_dm(
    guild: discord.Guild,
    role: discord.Role,
    embed: discord.Embed,
    *,
    delay: float | None = None,
    max_recipients: int | None = None,
) -> dict[str, Any]:
    """Send *embed* to humans with *role*. Refuses non-allowlisted roles and oversized batches."""
    if not is_allowed_notify_role(role.id):
        return {
            "sent": 0,
            "blocked": 0,
            "failed": 0,
            "skipped": 0,
            "error": "role_not_allowed",
        }
    if _broadcast_lock.locked():
        return {
            "sent": 0,
            "blocked": 0,
            "failed": 0,
            "skipped": 0,
            "error": "busy",
        }

    async with _broadcast_lock:
        members = await collect_role_members(guild, role)
        if not members:
            return {
                "sent": 0,
                "blocked": 0,
                "failed": 0,
                "skipped": 0,
                "error": "no_members",
            }
        limited = reject_if_over_limit(len(members), max_recipients)
        if limited is not None:
            return limited

        wait = PROMO_DM_DELAY_SECONDS if delay is None else delay
        sent = blocked = failed = 0
        for i, member in enumerate(members):
            if i:
                await asyncio.sleep(wait)
            view = PromoDmUnsubView(guild.id, role.id)
            try:
                await member.send(embed=embed, view=view)
                sent += 1
            except discord.Forbidden:
                blocked += 1
            except discord.HTTPException as exc:
                if exc.status == 429:
                    retry_after = float(getattr(exc, "retry_after", None) or 5)
                    await asyncio.sleep(retry_after)
                    try:
                        await member.send(embed=embed, view=PromoDmUnsubView(guild.id, role.id))
                        sent += 1
                    except discord.Forbidden:
                        blocked += 1
                    except Exception as retry_exc:
                        logger.warning("Promo DM retry failed for %s: %s", member.id, retry_exc)
                        failed += 1
                else:
                    logger.warning("Promo DM failed for %s: %s", member.id, exc)
                    failed += 1
            except Exception as exc:
                logger.warning("Promo DM failed for %s: %s", member.id, exc)
                failed += 1

        logger.info(
            "Promo DM to role %s: sent=%d blocked=%d failed=%d",
            role.id, sent, blocked, failed,
        )
        return {
            "sent": sent,
            "blocked": blocked,
            "failed": failed,
            "skipped": 0,
        }
