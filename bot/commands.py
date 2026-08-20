"""Slash commands for BigTreeSignal promotion, scheduling, and general bot utilities.

Provides:
- /signal          — Display product info embed
- /invite          — Create a personal referral invite
- /funnel          — Owner acquisition funnel snapshot
- /schedule_promo  — Owner schedules a promotional post
- /list_promos     — List pending / posted promotions
- /cancel_promo    — Cancel a scheduled promotion
- /post_promo      — Immediately post a promotion
- /dm_role         — Owner DMs an opt-in notify role
- /promo_notify_panel — Owner posts the subscribe panel
- /promo_notify    — Members subscribe/unsubscribe to notify roles
- /schedule_trial  — Owner schedules a free signal review post
- /schedule_lesson — Owner schedules an educational post (with repeat)
- /list_lessons    — List pending / posted lessons
- /cancel_lesson   — Cancel a scheduled lesson
- /testimonials    — Show recent approved testimonials
- /ask             — Public RAG query via slash command
- /status          — Bot uptime, queue depth, collection size
- /stats           — Query count, avg confidence, top questions
- /schedule_reminder — Owner schedules a reminder
- /list_reminders  — List pending reminders
- /cancel_reminder — Cancel a reminder
- /add_alert       — Add keyword alert
- /remove_alert    — Remove keyword alert
- /list_alerts     — List keyword alerts
- /kb_report       — Knowledge base report
- /kb_snapshots    — List KB snapshots
- /leaderboard     — Show activity leaderboard
- /ab_results      — A/B test results
- /export_conversations — Export conversations to JSON/CSV
- /pin_summary     — Summarize & pin a discussion
- /views           — Summarize owner's recent views into the current channel
- /satisfaction    — Satisfaction feedback stats
- /add_ban_word    — Add a word/phrase to the auto-mod ban list
- /remove_ban_word — Remove a word/phrase from the ban list
- /list_ban_words  — Show all banned words
"""

import io
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import (
    EXCLUDED_CHANNEL_IDS,
    KEYWORD_ALERT_ENABLED,
    OWNER_USER_ID,
    PROMO_CHANNEL_IDS,
    PROMO_ENABLED,
    TARGET_CHANNEL_IDS,
    VIP_ROLE_IDS,
)
from bot.health import uptime_seconds
from bot.promo_config import (
    get_signal_product_embed,
    is_promo_channel,
)
from bot.scheduler import (
    REPEAT_CHOICES,
    add_lesson,
    add_promo,
    cancel_lesson,
    cancel_promo,
    list_lessons,
    list_promos,
)
from bot.stats import bot_stats

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

_REPEAT_LABELS = {"none": "不重复", "hourly": "每小时", "daily": "每天", "weekly": "每周", "monthly": "每月"}
_REPEAT_APP_CHOICES = [
    app_commands.Choice(name=_REPEAT_LABELS[k], value=k) for k in REPEAT_CHOICES
]


def _is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_USER_ID


class PromotionCommands(commands.Cog):
    """Slash commands for BigTreeSignal promotion."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        from bot.role_dm import PromoNotifyView

        view = PromoNotifyView()
        if view.children:
            self.bot.add_view(view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if not isinstance(custom_id, str):
            return
        from bot.role_dm import handle_dm_unsub, handle_notify_toggle, parse_notify_toggle_custom_id

        if custom_id.startswith("promo_dm:unsub:"):
            await handle_dm_unsub(interaction, custom_id)
            return
        parsed = parse_notify_toggle_custom_id(custom_id)
        if parsed and parsed[2] is not None:
            subscribe, role_id, guild_id = parsed
            await handle_notify_toggle(interaction, role_id, subscribe, guild_id)

    # ── /signal ──────────────────────────────────────────────────────────────

    @app_commands.command(name="signal", description="了解 BigTreeSignal 交易信号产品")
    async def signal_info(self, interaction: discord.Interaction) -> None:
        if not PROMO_ENABLED:
            await interaction.response.send_message(
                "推广功能已关闭。", ephemeral=True,
            )
            return

        from bot.acquisition import build_cta_view, record_funnel
        embed = get_signal_product_embed()
        view = build_cta_view()
        record_funnel("signal_cmd")
        await interaction.response.send_message(embed=embed, view=view)

    # ── /invite ──────────────────────────────────────────────────────────────

    @app_commands.command(name="invite", description="生成你的专属邀请链接（邀请好友加入社群）")
    async def invite_cmd(self, interaction: discord.Interaction) -> None:
        from bot.acquisition import invite_count_for
        from bot.config import INVITE_REWARD_THRESHOLD, INVITE_TRACKING_ENABLED

        if not INVITE_TRACKING_ENABLED:
            await interaction.response.send_message("邀请功能未开启。", ephemeral=True)
            return
        if not interaction.guild or not isinstance(interaction.channel, discord.abc.GuildChannel):
            await interaction.response.send_message("请在服务器频道中使用此命令。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            channel = next((c for c in interaction.guild.text_channels if c.permissions_for(interaction.guild.me).create_instant_invite), None)
        if channel is None:
            await interaction.followup.send("无法在此频道创建邀请。", ephemeral=True)
            return
        try:
            invite = await channel.create_invite(
                max_age=0,
                max_uses=0,
                unique=True,
                reason=f"Referral invite for {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send("Bot 缺少创建邀请的权限。", ephemeral=True)
            return
        except Exception as exc:
            logger.warning("Failed to create referral invite: %s", exc)
            await interaction.followup.send("创建邀请失败，请稍后再试。", ephemeral=True)
            return

        count = invite_count_for(interaction.user.id)
        extra = ""
        if INVITE_REWARD_THRESHOLD > 0:
            extra = f"\n你已成功邀请 **{count}** 人（满 {INVITE_REWARD_THRESHOLD} 人可获奖励身份组）。"
        await interaction.followup.send(
            f"你的专属邀请链接：\n{invite.url}{extra}",
            ephemeral=True,
        )

    # ── /schedule_promo ──────────────────────────────────────────────────────

    @app_commands.command(
        name="schedule_promo",
        description="[Owner] 排程促销帖（到时间自动发送）",
    )
    @app_commands.describe(
        title="促销标题",
        description="促销详细描述",
        time="发送时间 (YYYY-MM-DD HH:MM, UTC-4)",
        url="促销链接（可选，默认用产品链接）",
        channel="发送到的频道（可选，默认所有推广频道）",
        repeat="重复模式",
        dm_role="同步私信给自愿通知身份组（可选，必须在白名单）",
    )
    @app_commands.choices(repeat=_REPEAT_APP_CHOICES)
    async def schedule_promo_cmd(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        time: str,
        url: str = "",
        channel: discord.TextChannel | None = None,
        repeat: app_commands.Choice[str] = None,
        dm_role: discord.Role | None = None,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        try:
            scheduled_at = datetime.strptime(time, "%Y-%m-%d %H:%M")
            scheduled_at = scheduled_at.replace(tzinfo=_ET)
        except ValueError:
            await interaction.response.send_message(
                "时间格式错误，请使用: `YYYY-MM-DD HH:MM`（例如 `2024-01-15 10:00`）",
                ephemeral=True,
            )
            return

        channel_ids = [channel.id] if channel else list(PROMO_CHANNEL_IDS)
        if not channel_ids:
            await interaction.response.send_message("未配置推广频道。", ephemeral=True)
            return

        if dm_role is not None:
            from bot.role_dm import notify_role_error

            err = notify_role_error(dm_role, required=True)
            if err:
                await interaction.response.send_message(err, ephemeral=True)
                return

        repeat_mode = repeat.value if repeat else "none"

        promo = add_promo(
            title=title,
            description=description,
            scheduled_at=scheduled_at,
            channel_ids=channel_ids,
            created_by=interaction.user.id,
            url=url,
            repeat=repeat_mode,
            dm_role_id=dm_role.id if dm_role else None,
        )

        repeat_label = _REPEAT_LABELS.get(repeat_mode, repeat_mode)
        dm_line = f"\n**私信身份组:** {dm_role.mention}" if dm_role else ""
        await interaction.response.send_message(
            f"✅ 促销已排程！\n"
            f"**ID:** `{promo['id']}`\n"
            f"**标题:** {title}\n"
            f"**发送时间:** {scheduled_at.strftime('%Y-%m-%d %H:%M')} (ET)\n"
            f"**重复:** {repeat_label}\n"
            f"**频道:** {len(channel_ids)} 个{dm_line}",
            ephemeral=True,
        )

    # ── /list_promos ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="list_promos",
        description="[Owner] 列出所有排程的促销",
    )
    async def list_promos_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        promos = list_promos()
        if not promos:
            await interaction.response.send_message("没有排程的促销。", ephemeral=True)
            return

        lines = []
        for p in promos[-10:]:
            status = "✅ 已发送" if p.get("posted") else "⏳ 待发送"
            lines.append(
                f"{status} `{p['id']}` — **{p['title']}** — "
                f"{p['scheduled_at'][:16]}"
            )
        await interaction.response.send_message(
            "**排程促销列表：**\n" + "\n".join(lines),
            ephemeral=True,
        )

    # ── /cancel_promo ────────────────────────────────────────────────────────

    @app_commands.command(
        name="cancel_promo",
        description="[Owner] 取消一个排程的促销",
    )
    @app_commands.describe(promo_id="促销 ID")
    async def cancel_promo_cmd(
        self,
        interaction: discord.Interaction,
        promo_id: str,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        if cancel_promo(promo_id):
            await interaction.response.send_message(
                f"✅ 促销 `{promo_id}` 已取消。", ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"找不到促销 `{promo_id}`（可能已发送或不存在）。", ephemeral=True,
            )

    # ── /post_promo ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="post_promo",
        description="[Owner] 立即发送促销帖（不排程）",
    )
    @app_commands.describe(
        title="促销标题",
        description="促销详细描述",
        url="促销链接（可选）",
        channel="发送到的频道（可选，默认所有推广频道）",
        dm_role="同步私信给自愿通知身份组（可选，必须在白名单）",
    )
    async def post_promo_cmd(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        url: str = "",
        channel: discord.TextChannel | None = None,
        dm_role: discord.Role | None = None,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        if dm_role is not None:
            from bot.role_dm import notify_role_error

            err = notify_role_error(dm_role, required=True)
            if err:
                await interaction.response.send_message(err, ephemeral=True)
                return

        from bot.config import SIGNAL_PRODUCT_URL
        link = url or SIGNAL_PRODUCT_URL

        embed = discord.Embed(
            title=f"🌳 {title}",
            description=description,
            color=discord.Color.gold(),
        )
        if link:
            embed.add_field(name="🔗 链接", value=f"[点击查看]({link})", inline=False)

        channel_ids = [channel.id] if channel else list(PROMO_CHANNEL_IDS)
        if not channel_ids:
            await interaction.response.send_message("未配置推广频道。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        sent = 0
        for cid in channel_ids:
            from bot.utils import resolve_channel
            ch = await resolve_channel(self.bot, cid)
            if ch:
                try:
                    await ch.send(embed=embed)
                    sent += 1
                except Exception as exc:
                    logger.warning("Failed to post promo to channel %d: %s", cid, exc)
            else:
                logger.warning("Promo post: channel %s not found or not messageable", cid)

        msg = f"✅ 促销已发送到 {sent}/{len(channel_ids)} 个频道。"
        if dm_role is None:
            await interaction.followup.send(msg, ephemeral=True)
            return
        if interaction.guild is None:
            await interaction.followup.send(msg + "\n请在服务器频道中使用私信选项。", ephemeral=True)
            return

        from bot.role_dm import (
            RoleDmConfirmView,
            collect_role_members,
            format_broadcast_result,
            reject_if_over_limit,
        )

        members = await collect_role_members(interaction.guild, dm_role)
        limited = reject_if_over_limit(len(members))
        if limited is not None:
            await interaction.followup.send(
                msg + "\n" + format_broadcast_result(limited), ephemeral=True,
            )
            return
        if not members:
            await interaction.followup.send(
                msg + "\n该通知身份组目前没有成员。请先发 `/promo_notify_panel` 让成员自愿领取。",
                ephemeral=True,
            )
            return

        view = RoleDmConfirmView(
            guild_id=interaction.guild.id,
            role_id=dm_role.id,
            title=title,
            description=description,
            url=url,
            owner_id=interaction.user.id,
        )
        await interaction.followup.send(
            f"{msg}\n将向 {dm_role.mention} 的 **{len(members)}** 人发送私信，确认？",
            view=view,
            ephemeral=True,
        )

    # ── /dm_role ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="dm_role",
        description="[Owner] 向自愿通知身份组发送促销私信（不发频道）",
    )
    @app_commands.describe(
        role="白名单里的通知身份组",
        title="促销标题",
        description="促销详细描述",
        url="促销链接（可选）",
    )
    async def dm_role_cmd(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        title: str,
        description: str,
        url: str = "",
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        if interaction.guild is None:
            await interaction.response.send_message("请在服务器频道中使用此命令。", ephemeral=True)
            return

        from bot.role_dm import (
            RoleDmConfirmView,
            collect_role_members,
            format_broadcast_result,
            notify_role_error,
            reject_if_over_limit,
        )

        err = notify_role_error(role, required=True)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        members = await collect_role_members(interaction.guild, role)
        limited = reject_if_over_limit(len(members))
        if limited is not None:
            await interaction.followup.send(format_broadcast_result(limited), ephemeral=True)
            return
        if not members:
            await interaction.followup.send(
                "该通知身份组目前没有成员。请先发 `/promo_notify_panel` 让成员自愿领取。",
                ephemeral=True,
            )
            return

        view = RoleDmConfirmView(
            guild_id=interaction.guild.id,
            role_id=role.id,
            title=title,
            description=description,
            url=url,
            owner_id=interaction.user.id,
        )
        await interaction.followup.send(
            f"将向 {role.mention} 的 **{len(members)}** 人发送私信，确认？",
            view=view,
            ephemeral=True,
        )

    # ── /promo_notify_panel ──────────────────────────────────────────────────

    @app_commands.command(
        name="promo_notify_panel",
        description="[Owner] 在频道发布活动私信订阅面板",
    )
    @app_commands.describe(channel="发送到的频道（可选，默认当前频道）")
    async def promo_notify_panel_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.config import PROMO_NOTIFY_ROLE_IDS
        from bot.role_dm import PromoNotifyView, build_notify_panel_embed, notify_role_error

        err = notify_role_error(None, required=False)
        if not PROMO_NOTIFY_ROLE_IDS:
            await interaction.response.send_message(
                err or "未配置 PROMO_NOTIFY_ROLE_IDS。",
                ephemeral=True,
            )
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message("请指定一个文字频道。", ephemeral=True)
            return

        guild = interaction.guild or target.guild
        embed = build_notify_panel_embed(guild)
        view = PromoNotifyView(guild)
        if len(view.children) == 0:
            await interaction.response.send_message(
                "白名单为空，无法生成订阅按钮。", ephemeral=True,
            )
            return
        try:
            await target.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"无法在 {target.mention} 发消息，请检查 Bot 权限。", ephemeral=True,
            )
            return
        except Exception as exc:
            logger.warning("Failed to post notify panel: %s", exc)
            await interaction.response.send_message("发送订阅面板失败。", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ 已在 {target.mention} 发布订阅面板。建议置顶，并可在频道里 @everyone 提醒一次。",
            ephemeral=True,
        )

    # ── /promo_notify ────────────────────────────────────────────────────────

    @app_commands.command(
        name="promo_notify",
        description="领取或取消活动私信通知身份组",
    )
    @app_commands.describe(
        action="subscribe=领取，unsubscribe=取消",
        role="白名单通知身份组（可选，默认第一个）",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="领取", value="subscribe"),
            app_commands.Choice(name="取消", value="unsubscribe"),
        ]
    )
    async def promo_notify_cmd(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        role: discord.Role | None = None,
    ) -> None:
        from bot.role_dm import apply_notify_role, default_notify_role_id, notify_role_error, status_message

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("请在服务器频道中使用此命令。", ephemeral=True)
            return

        target_role = role
        if target_role is None:
            rid = default_notify_role_id()
            if rid:
                target_role = interaction.guild.get_role(rid)
        err = notify_role_error(target_role, required=True)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        if target_role is None:
            await interaction.response.send_message(
                "找不到通知身份组，请确认 `PROMO_NOTIFY_ROLE_IDS` 正确。",
                ephemeral=True,
            )
            return

        subscribe = action.value == "subscribe"
        status = await apply_notify_role(interaction.user, target_role, subscribe)
        await interaction.response.send_message(status_message(status, target_role), ephemeral=True)

    # ── /schedule_trial ──────────────────────────────────────────────────────

    @app_commands.command(
        name="schedule_trial",
        description="[Owner] 排程免费信号回顾帖",
    )
    @app_commands.describe(
        title="标题（如：今日免费信号回顾）",
        content="回顾内容",
        time="发送时间 (YYYY-MM-DD HH:MM, UTC-4)",
        channel="发送到的频道（可选）",
        repeat="重复模式",
    )
    @app_commands.choices(repeat=_REPEAT_APP_CHOICES)
    async def schedule_trial_cmd(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        time: str,
        channel: discord.TextChannel | None = None,
        repeat: app_commands.Choice[str] = None,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        try:
            scheduled_at = datetime.strptime(time, "%Y-%m-%d %H:%M")
            scheduled_at = scheduled_at.replace(tzinfo=_ET)
        except ValueError:
            await interaction.response.send_message(
                "时间格式错误，请使用: `YYYY-MM-DD HH:MM`", ephemeral=True,
            )
            return

        channel_ids = [channel.id] if channel else list(PROMO_CHANNEL_IDS)
        if not channel_ids:
            await interaction.response.send_message("未配置推广频道。", ephemeral=True)
            return

        repeat_mode = repeat.value if repeat else "none"

        promo = add_promo(
            title=title,
            description=content,
            scheduled_at=scheduled_at,
            channel_ids=channel_ids,
            created_by=interaction.user.id,
            promo_type="trial_signal",
            repeat=repeat_mode,
        )

        repeat_label = _REPEAT_LABELS.get(repeat_mode, repeat_mode)
        await interaction.response.send_message(
            f"✅ 信号回顾帖已排程！\n"
            f"**ID:** `{promo['id']}`\n"
            f"**发送时间:** {scheduled_at.strftime('%Y-%m-%d %H:%M')} (ET)\n"
            f"**重复:** {repeat_label}",
            ephemeral=True,
        )

    # ── /schedule_lesson ─────────────────────────────────────────────────────

    @app_commands.command(
        name="schedule_lesson",
        description="[Owner] 排程教学内容推送（支持重复）",
    )
    @app_commands.describe(
        title="教学标题",
        content="教学内容",
        time="首次发送时间 (YYYY-MM-DD HH:MM, UTC-4)",
        repeat="重复模式",
        channel="发送到的频道（可选）",
    )
    @app_commands.choices(repeat=_REPEAT_APP_CHOICES)
    async def schedule_lesson_cmd(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        time: str,
        repeat: app_commands.Choice[str] = None,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        try:
            scheduled_at = datetime.strptime(time, "%Y-%m-%d %H:%M")
            scheduled_at = scheduled_at.replace(tzinfo=_ET)
        except ValueError:
            await interaction.response.send_message(
                "时间格式错误，请使用: `YYYY-MM-DD HH:MM`", ephemeral=True,
            )
            return

        channel_ids = [channel.id] if channel else list(PROMO_CHANNEL_IDS)
        if not channel_ids:
            await interaction.response.send_message("未配置推广频道。", ephemeral=True)
            return

        repeat_mode = repeat.value if repeat else "none"

        lesson = add_lesson(
            title=title,
            content=content,
            scheduled_at=scheduled_at,
            channel_ids=channel_ids,
            created_by=interaction.user.id,
            repeat=repeat_mode,
        )

        repeat_label = _REPEAT_LABELS.get(repeat_mode, repeat_mode)

        await interaction.response.send_message(
            f"✅ 教学帖已排程！\n"
            f"**ID:** `{lesson['id']}`\n"
            f"**标题:** {title}\n"
            f"**发送时间:** {scheduled_at.strftime('%Y-%m-%d %H:%M')} (ET)\n"
            f"**重复:** {repeat_label}",
            ephemeral=True,
        )

    # ── /list_lessons ────────────────────────────────────────────────────────

    @app_commands.command(
        name="list_lessons",
        description="[Owner] 列出所有排程的教学帖",
    )
    async def list_lessons_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        lessons = list_lessons()
        if not lessons:
            await interaction.response.send_message("没有排程的教学帖。", ephemeral=True)
            return

        lines = []
        for ls in lessons[-10:]:
            repeat_label = {"none": "单次", "daily": "每天", "weekly": "每周"}.get(
                ls.get("repeat", "none"), ls.get("repeat", "none")
            )
            lines.append(
                f"`{ls['id']}` — **{ls['title']}** — "
                f"{ls['scheduled_at'][:16]} ({repeat_label})"
            )
        await interaction.response.send_message(
            "**排程教学列表：**\n" + "\n".join(lines),
            ephemeral=True,
        )

    # ── /cancel_lesson ───────────────────────────────────────────────────────

    @app_commands.command(
        name="cancel_lesson",
        description="[Owner] 取消一个排程的教学帖",
    )
    @app_commands.describe(lesson_id="教学帖 ID")
    async def cancel_lesson_cmd(
        self,
        interaction: discord.Interaction,
        lesson_id: str,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        if cancel_lesson(lesson_id):
            await interaction.response.send_message(
                f"✅ 教学帖 `{lesson_id}` 已取消。", ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"找不到教学帖 `{lesson_id}`。", ephemeral=True,
            )

    # ── /testimonials ────────────────────────────────────────────────────────

    @app_commands.command(
        name="testimonials",
        description="展示最近的用户好评见证",
    )
    async def testimonials_cmd(self, interaction: discord.Interaction) -> None:
        if not is_promo_channel(interaction.channel_id):
            await interaction.response.send_message(
                "此频道未开启推广功能。", ephemeral=True,
            )
            return

        from bot.testimonials import get_approved_testimonials

        testimonials = get_approved_testimonials(limit=5)
        if not testimonials:
            await interaction.response.send_message(
                "暂无用户见证。", ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🌟 用户好评",
            description="来自社群成员的真实反馈",
            color=discord.Color.gold(),
        )
        for t in testimonials:
            name = t.get("author_name", "社群成员")
            text = t.get("content", "")[:200]
            timestamp = t.get("timestamp", "")[:10]
            embed.add_field(
                name=f"💬 {name} — {timestamp}",
                value=text,
                inline=False,
            )
        await interaction.response.send_message(embed=embed)


class BotCommands(commands.Cog):
    """General-purpose slash commands for the RAG bot."""

    def __init__(
        self,
        bot: commands.Bot,
        collection,
        openai_client,
    ):
        self.bot = bot
        self.collection = collection
        self.openai_client = openai_client

    # ── /ask ─────────────────────────────────────────────────────────────

    @app_commands.command(name="ask", description="向AI助手提问（使用RAG知识库）")
    @app_commands.describe(question="你的问题")
    async def ask_cmd(self, interaction: discord.Interaction, question: str) -> None:
        if EXCLUDED_CHANNEL_IDS and interaction.channel_id in EXCLUDED_CHANNEL_IDS:
            await interaction.response.send_message(
                "此频道未开启问答功能。", ephemeral=True,
            )
            return
        if TARGET_CHANNEL_IDS and interaction.channel_id not in TARGET_CHANNEL_IDS:
            await interaction.response.send_message(
                "此频道未开启问答功能。", ephemeral=True,
            )
            return

        await interaction.response.defer()  # may take a few seconds

        from bot.confidence import route_answer
        from bot.rag import run_rag_pipeline

        answer, confidence, context_chunks = await run_rag_pipeline(
            question=question,
            collection=self.collection,
            openai_client=self.openai_client,
        )

        best_distance = 1.0
        if context_chunks:
            best_distance = min(c.get("distance", 1.0) for c in context_chunks)

        routing = route_answer(
            answer=answer,
            confidence=confidence,
            context_count=len(context_chunks),
            best_distance=best_distance,
            question=question,
        )

        if routing["action"] == "auto_reply":
            embed = discord.Embed(
                description=routing["answer"][:4096],
                color=discord.Color.green() if confidence >= 7 else discord.Color.orange(),
            )
            embed.set_footer(text=f"Confidence: {confidence}/10")
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                description="这个问题需要频道主确认后才能回答，已转发给频道主审核。",
                color=discord.Color.orange(),
            )
            embed.set_footer(text=f"Reason: {routing['reason']}")
            await interaction.followup.send(embed=embed, ephemeral=True)
            # Forward to owner for review
            from bot.review import send_for_review
            # Create a lightweight proxy for the interaction message
            try:
                original = await interaction.original_response()
                await send_for_review(
                    bot=self.bot,
                    original_message=original,
                    draft_answer=routing["answer"],
                    confidence=confidence,
                    context_snippets=context_chunks[:3] if context_chunks else None,
                    collection=self.collection,
                    openai_client=self.openai_client,
                )
            except Exception as exc:
                logger.warning("Failed to forward /ask query for review: %s", exc)

    # ── /status ──────────────────────────────────────────────────────────

    @app_commands.command(name="status", description="[开发] 查看机器人状态")
    async def status_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        uptime_min = round(uptime_seconds() / 60, 1)
        latency_ms = round(self.bot.latency * 1000, 1)
        guilds = len(self.bot.guilds) if self.bot.guilds else 0

        try:
            doc_count = await self.collection.count()
        except Exception:
            doc_count = "N/A"

        # Get queue depth from MessageListener cog if available
        listener = self.bot.get_cog("MessageListener")
        queue_depth = listener._queue.qsize() if listener else "N/A"

        embed = discord.Embed(title="🤖 Bot Status", color=discord.Color.blue())
        embed.add_field(name="Uptime", value=f"{uptime_min} min", inline=True)
        embed.add_field(name="WS Latency", value=f"{latency_ms} ms", inline=True)
        embed.add_field(name="Guilds", value=str(guilds), inline=True)
        embed.add_field(name="KB Documents", value=str(doc_count), inline=True)
        embed.add_field(name="Queue Depth", value=str(queue_depth), inline=True)
        embed.add_field(name="Total Queries", value=str(bot_stats.total_queries), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /stats ───────────────────────────────────────────────────────────

    @app_commands.command(name="stats", description="[开发] 查看查询统计")
    async def stats_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        snap = bot_stats.snapshot()
        embed = discord.Embed(title="📊 Query Statistics", color=discord.Color.purple())
        embed.add_field(name="Total Queries", value=str(snap["total_queries"]), inline=True)
        embed.add_field(name="Auto-Replies", value=str(snap["auto_replies"]), inline=True)
        embed.add_field(name="Forwards", value=str(snap["forwards"]), inline=True)
        embed.add_field(name="Avg Confidence", value=str(snap["avg_confidence"]), inline=True)
        embed.add_field(name="Avg Latency", value=f"{snap['avg_latency_ms']} ms", inline=True)

        recent = bot_stats.top_questions(5)
        if recent:
            lines = []
            for r in recent:
                action_icon = "✅" if r["action"] == "auto_reply" else "📩"
                lines.append(f"{action_icon} (c={r['confidence']}) {r['question'][:60]}")
            embed.add_field(
                name="Recent Queries",
                value="\n".join(lines),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /funnel ──────────────────────────────────────────────────────────

    @app_commands.command(name="funnel", description="[Owner] 查看获客转化漏斗")
    @app_commands.describe(days="统计天数（默认7）")
    async def funnel_cmd(self, interaction: discord.Interaction, days: int = 7) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        from bot.acquisition import funnel_snapshot

        days = max(1, min(90, days))
        snap = funnel_snapshot(days)
        window = snap["window"]
        life = snap["lifetime"]
        embed = discord.Embed(
            title=f"📈 获客漏斗（近 {days} 天）",
            color=discord.Color.green(),
        )
        embed.add_field(name="新加入", value=str(window["joins"]), inline=True)
        embed.add_field(name="欢迎DM成功", value=str(window["welcome_dm_ok"]), inline=True)
        embed.add_field(name="欢迎DM被拒", value=str(window["welcome_dm_blocked"]), inline=True)
        embed.add_field(name="/signal 使用", value=str(window["signal_cmd"]), inline=True)
        embed.add_field(name="购买意向", value=str(window["intent_hits"]), inline=True)
        embed.add_field(name="CTA 发送", value=str(window["cta_posts"]), inline=True)
        embed.add_field(name="邀请加入", value=str(window["invite_joins"]), inline=True)
        embed.add_field(
            name="累计（上线以来）",
            value=(
                f"加入 {life['joins']} · DM成功 {life['welcome_dm_ok']} · "
                f"/signal {life['signal_cmd']} · 意向 {life['intent_hits']} · "
                f"邀请 {life['invite_joins']}"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /search_kb ────────────────────────────────────────────────────────

    @app_commands.command(name="search_kb", description="[Owner] 搜索知识库文档")
    @app_commands.describe(query="搜索关键词", top_k="返回数量 (1-10, 默认5)")
    async def search_kb_cmd(
        self,
        interaction: discord.Interaction,
        query: str,
        top_k: int = 5,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        top_k = max(1, min(10, top_k))

        from bot.rag import retrieve_context

        try:
            chunks = await retrieve_context(
                question=query,
                collection=self.collection,
                openai_client=self.openai_client,
                top_k=top_k,
            )
        except Exception as exc:
            await interaction.followup.send(f"搜索失败: {exc}", ephemeral=True)
            return

        if not chunks:
            await interaction.followup.send("未找到匹配的文档。", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🔍 KB Search: {query[:100]}",
            description=f"找到 {len(chunks)} 个匹配文档",
            color=discord.Color.blue(),
        )
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "")[:200]
            dist = chunk.get("distance", 0)
            meta = chunk.get("metadata", {})
            doc_type = meta.get("type", "unknown")
            embed.add_field(
                name=f"{i}. [{doc_type}] (dist: {dist:.3f})",
                value=text + "…" if len(chunk.get("text", "")) > 200 else text,
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /faq ──────────────────────────────────────────────────────────────

    @app_commands.command(name="faq", description="查看常见问题 (FAQ)")
    async def faq_cmd(self, interaction: discord.Interaction) -> None:
        from bot.faq import get_cached_faq

        items = get_cached_faq()
        if not items:
            await interaction.response.send_message(
                "暂无FAQ。频道主可以使用 `/generate_faq` 生成。", ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📋 常见问题 FAQ",
            color=discord.Color.teal(),
        )
        for i, item in enumerate(items[:10], 1):
            embed.add_field(
                name=f"{i}. {item['q']}",
                value=item["a"][:1024],
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    # ── /generate_faq ─────────────────────────────────────────────────────

    @app_commands.command(
        name="generate_faq",
        description="[Owner] 根据高频问题自动生成FAQ",
    )
    async def generate_faq_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        from bot.faq import generate_faq

        items = await generate_faq(self.openai_client)

        if not items:
            await interaction.followup.send("FAQ生成失败，高频问题不足或生成出错。", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 FAQ 已生成",
            description=f"共 {len(items)} 个条目",
            color=discord.Color.teal(),
        )
        for i, item in enumerate(items[:10], 1):
            embed.add_field(
                name=f"{i}. {item['q']}",
                value=item["a"][:1024],
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /schedule_reminder ───────────────────────────────────────────────

    @app_commands.command(
        name="schedule_reminder",
        description="[Owner] 排程提醒消息（如市场开盘提醒）",
    )
    @app_commands.describe(
        title="提醒标题",
        message="提醒内容",
        time="发送时间 (YYYY-MM-DD HH:MM, UTC-4)",
        repeat="重复模式",
        channel="发送到的频道（可选）",
    )
    @app_commands.choices(repeat=_REPEAT_APP_CHOICES)
    async def schedule_reminder_cmd(
        self,
        interaction: discord.Interaction,
        title: str,
        message: str,
        time: str,
        repeat: app_commands.Choice[str] = None,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        try:
            scheduled_at = datetime.strptime(time, "%Y-%m-%d %H:%M")
            scheduled_at = scheduled_at.replace(tzinfo=_ET)
        except ValueError:
            await interaction.response.send_message(
                "时间格式错误，请使用: `YYYY-MM-DD HH:MM`", ephemeral=True,
            )
            return
        channel_ids = [channel.id] if channel else list(PROMO_CHANNEL_IDS)
        if not channel_ids:
            channel_ids = list(TARGET_CHANNEL_IDS) if TARGET_CHANNEL_IDS else []
        if not channel_ids:
            await interaction.response.send_message("未配置频道。", ephemeral=True)
            return
        repeat_mode = repeat.value if repeat else "none"
        from bot.reminders import add_reminder
        rem = add_reminder(
            title=title, message=message, scheduled_at=scheduled_at,
            channel_ids=channel_ids, created_by=interaction.user.id,
            repeat=repeat_mode,
        )
        repeat_label = _REPEAT_LABELS.get(repeat_mode, repeat_mode)
        await interaction.response.send_message(
            f"✅ 提醒已排程！\n**ID:** `{rem['id']}`\n**标题:** {title}\n"
            f"**发送时间:** {scheduled_at.strftime('%Y-%m-%d %H:%M')} (ET)\n"
            f"**重复:** {repeat_label}",
            ephemeral=True,
        )

    # ── /list_reminders ──────────────────────────────────────────────────

    @app_commands.command(name="list_reminders", description="[Owner] 列出所有排程的提醒")
    async def list_reminders_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.reminders import list_reminders
        rems = list_reminders()
        if not rems:
            await interaction.response.send_message("没有排程的提醒。", ephemeral=True)
            return
        lines = []
        for r in rems[-10:]:
            repeat_label = _REPEAT_LABELS.get(r.get("repeat", "none"), r.get("repeat", "none"))
            lines.append(f"`{r['id']}` — **{r['title']}** — {r['scheduled_at'][:16]} ({repeat_label})")
        await interaction.response.send_message("**排程提醒列表：**\n" + "\n".join(lines), ephemeral=True)

    # ── /cancel_reminder ─────────────────────────────────────────────────

    @app_commands.command(name="cancel_reminder", description="[Owner] 取消一个排程的提醒")
    @app_commands.describe(reminder_id="提醒 ID")
    async def cancel_reminder_cmd(self, interaction: discord.Interaction, reminder_id: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.reminders import cancel_reminder
        if cancel_reminder(reminder_id):
            await interaction.response.send_message(f"✅ 提醒 `{reminder_id}` 已取消。", ephemeral=True)
        else:
            await interaction.response.send_message(f"找不到提醒 `{reminder_id}`。", ephemeral=True)

    # ── /add_alert ───────────────────────────────────────────────────────

    @app_commands.command(name="add_alert", description="[Owner] 添加关键词监控（出现时DM通知）")
    @app_commands.describe(keyword="要监控的关键词")
    async def add_alert_cmd(self, interaction: discord.Interaction, keyword: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.keyword_alert import add_keyword
        if add_keyword(keyword):
            await interaction.response.send_message(f"✅ 关键词 `{keyword}` 已添加到监控列表。", ephemeral=True)
        else:
            await interaction.response.send_message(f"关键词 `{keyword}` 已存在。", ephemeral=True)

    # ── /remove_alert ────────────────────────────────────────────────────

    @app_commands.command(name="remove_alert", description="[Owner] 移除关键词监控")
    @app_commands.describe(keyword="要移除的关键词")
    async def remove_alert_cmd(self, interaction: discord.Interaction, keyword: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.keyword_alert import remove_keyword
        if remove_keyword(keyword):
            await interaction.response.send_message(f"✅ 关键词 `{keyword}` 已移除。", ephemeral=True)
        else:
            await interaction.response.send_message(f"关键词 `{keyword}` 不在列表中。", ephemeral=True)

    # ── /list_alerts ─────────────────────────────────────────────────────

    @app_commands.command(name="list_alerts", description="[Owner] 列出所有监控关键词")
    async def list_alerts_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.keyword_alert import get_keywords
        keywords = get_keywords()
        if not keywords:
            await interaction.response.send_message("没有设置监控关键词。", ephemeral=True)
            return
        await interaction.response.send_message(
            "**监控关键词：**\n" + ", ".join(f"`{k}`" for k in keywords),
            ephemeral=True,
        )

    # ── /kb_report ───────────────────────────────────────────────────────

    @app_commands.command(name="kb_report", description="[Owner] 知识库质量报告")
    async def kb_report_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        try:
            doc_count = await self.collection.count()
        except Exception:
            doc_count = 0

        snap = bot_stats.snapshot()
        low_conf_count = sum(
            1 for r in bot_stats._filter_by_range("30d") if r.confidence <= 3
        )
        total_30d = len(bot_stats._filter_by_range("30d"))

        from bot.feedback import satisfaction_stats
        sat = satisfaction_stats(30)

        embed = discord.Embed(
            title="📊 知识库质量报告",
            color=discord.Color.blue(),
        )
        embed.add_field(name="📚 文档总数", value=str(doc_count), inline=True)
        embed.add_field(name="📈 30天查询数", value=str(total_30d), inline=True)
        embed.add_field(name="⚠️ 低置信度查询", value=f"{low_conf_count} ({round(low_conf_count/total_30d*100, 1) if total_30d else 0}%)", inline=True)
        embed.add_field(name="👍 满意度", value=f"{sat['satisfaction_rate']}% ({sat['total']} 评价)", inline=True)
        embed.add_field(name="📊 平均置信度", value=str(snap["avg_confidence"]), inline=True)
        embed.add_field(name="⏱️ 平均延迟", value=f"{snap['avg_latency_ms']} ms", inline=True)

        from bot.leaderboard import top_questions_by_frequency
        freq = top_questions_by_frequency(5, 30)
        if freq:
            lines = [f"• {q['question'][:60]} (x{q['count']})" for q in freq]
            embed.add_field(name="🔥 高频问题", value="\n".join(lines), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /kb_snapshots ────────────────────────────────────────────────────

    @app_commands.command(name="kb_snapshots", description="[Owner] 查看知识库快照")
    async def kb_snapshots_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.kb_versioning import list_snapshots
        snapshots = list_snapshots()
        if not snapshots:
            await interaction.response.send_message("没有知识库快照。", ephemeral=True)
            return
        lines = []
        for s in snapshots[:10]:
            from datetime import datetime as _dt
            ts = _dt.fromtimestamp(s["timestamp"]).strftime("%Y-%m-%d %H:%M")
            lines.append(f"`{s['id']}` — {ts} — {s['doc_count']} docs — {s.get('description', '')[:50]}")
        await interaction.response.send_message("**知识库快照：**\n" + "\n".join(lines), ephemeral=True)

    # ── /leaderboard ─────────────────────────────────────────────────────

    @app_commands.command(name="leaderboard", description="[Owner] 查看活跃度排行榜")
    @app_commands.describe(days="统计天数 (默认30)")
    async def leaderboard_cmd(self, interaction: discord.Interaction, days: int = 30) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.leaderboard import top_questioners, confidence_distribution

        top = top_questioners(10, days)
        dist = confidence_distribution(days)

        embed = discord.Embed(
            title=f"🏆 活跃度排行榜 (最近 {days} 天)",
            color=discord.Color.gold(),
        )
        if top:
            lines = []
            for i, t in enumerate(top, 1):
                medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
                lines.append(f"{medal} 频道 `{t['channel_id']}` — {t['count']} 次查询")
            embed.add_field(name="最活跃频道", value="\n".join(lines), inline=False)

        dist_lines = [f"• {k}: {v} 次" for k, v in dist.items()]
        embed.add_field(name="置信度分布", value="\n".join(dist_lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /ab_results ──────────────────────────────────────────────────────

    @app_commands.command(name="ab_results", description="[Owner] 查看A/B测试结果")
    async def ab_results_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.ab_test import get_results, AB_TEST_ENABLED
        if not AB_TEST_ENABLED:
            await interaction.response.send_message("A/B测试未启用。设置 `AB_TEST_ENABLED=true` 启用。", ephemeral=True)
            return
        results = get_results()
        if not results:
            await interaction.response.send_message("暂无A/B测试数据。", ephemeral=True)
            return
        embed = discord.Embed(title="🔬 A/B 测试结果", color=discord.Color.purple())
        for variant, data in results.items():
            embed.add_field(
                name=f"变体: {variant}",
                value=f"总数: {data['total']} | 👍 {data['positive']} | 👎 {data['negative']} | 满意率: {data['satisfaction_rate']}%",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /export_conversations ────────────────────────────────────────────

    @app_commands.command(name="export_conversations", description="[Owner] 导出对话记录")
    @app_commands.describe(
        format="导出格式",
        days="导出天数 (默认30)",
    )
    @app_commands.choices(format=[
        app_commands.Choice(name="JSON", value="json"),
        app_commands.Choice(name="CSV", value="csv"),
    ])
    async def export_conversations_cmd(
        self,
        interaction: discord.Interaction,
        format: app_commands.Choice[str] = None,
        days: int = 30,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        from bot.export import export_json, export_csv, export_count
        fmt = format.value if format else "json"
        count = export_count(days)
        if count == 0:
            await interaction.followup.send("没有可导出的对话记录。", ephemeral=True)
            return
        if fmt == "csv":
            data = export_csv(days)
            filename = "conversations.csv"
        else:
            data = export_json(days)
            filename = "conversations.json"
        file = discord.File(io.BytesIO(data.encode("utf-8")), filename=filename)
        await interaction.followup.send(
            f"✅ 导出 {count} 条记录 ({days} 天)", file=file, ephemeral=True,
        )

    # ── /pin_summary ─────────────────────────────────────────────────────

    @app_commands.command(name="pin_summary", description="[Owner] 总结最近的讨论并钉到频道")
    @app_commands.describe(count="要总结的消息数量 (默认20)")
    async def pin_summary_cmd(self, interaction: discord.Interaction, count: int = 20) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        count = max(5, min(50, count))
        messages = []
        async for msg in interaction.channel.history(limit=count, oldest_first=False):
            if msg.content and msg.content.strip():
                messages.append(msg)
        messages.reverse()
        if len(messages) < 3:
            await interaction.followup.send("消息不足，无法生成摘要。", ephemeral=True)
            return
        text_parts = []
        for msg in messages:
            author = str(msg.author.display_name)
            text_parts.append(f"{author}: {msg.content[:300]}")
        conversation_text = "\n".join(text_parts)
        from bot.rag import _openai_chat_with_retry
        summary = await _openai_chat_with_retry(
            self.openai_client,
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一个社群讨论摘要助手。请用简洁的中文总结以下讨论的要点，列出关键观点。不超过500字。"},
                {"role": "user", "content": f"请总结以下讨论：\n\n{conversation_text}"},
            ],
            max_tokens=600,
        )
        if not summary:
            await interaction.followup.send("摘要生成失败。", ephemeral=True)
            return
        embed = discord.Embed(
            title="📌 讨论摘要",
            description=summary[:4096],
            color=discord.Color.dark_green(),
        )
        embed.set_footer(text=f"基于最近 {len(messages)} 条消息生成")
        summary_msg = await interaction.channel.send(embed=embed)
        try:
            await summary_msg.pin()
        except discord.Forbidden:
            pass
        await interaction.followup.send("✅ 摘要已生成并钉到频道。", ephemeral=True)

    # ── /views ───────────────────────────────────────────────────────────

    @app_commands.command(
        name="views",
        description="[Owner] 总结我最近的观点看法并发送到本频道",
    )
    @app_commands.describe(hours="回溯小时数（1–168，默认 24）")
    async def views_cmd(
        self,
        interaction: discord.Interaction,
        hours: app_commands.Range[int, 1, 168] = 24,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return

        from bot.views_summary import (
            clamp_views_hours,
            count_owner_view_rows,
            gather_views_messages,
            generate_views_summary,
            is_guild_text_target,
        )
        from bot.weekly_summary import format_messages_for_gpt

        if not is_guild_text_target(interaction.channel, interaction.guild):
            await interaction.response.send_message(
                "请在服务器的文字频道或帖子里使用此命令。", ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        hours = clamp_views_hours(hours)

        try:
            messages, dm_note = await gather_views_messages(
                self.bot, interaction.channel, hours, include_dms=True,
            )
        except Exception:
            logger.exception("views: failed to collect messages")
            await interaction.followup.send("收集发言失败，请稍后再试。", ephemeral=True)
            return

        if not messages:
            await interaction.followup.send(
                f"最近 {hours} 小时内，在本服务器各频道没有找到你的发言，无法生成观点总结。\n{dm_note}",
                ephemeral=True,
            )
            return

        messages_text = format_messages_for_gpt(messages)
        try:
            summary = await generate_views_summary(self.openai_client, messages_text)
        except Exception:
            logger.exception("views command GPT error")
            await interaction.followup.send("生成失败，请稍后再试。", ephemeral=True)
            return

        if not summary:
            await interaction.followup.send("生成结果为空，请稍后再试。", ephemeral=True)
            return

        owner_n = count_owner_view_rows(messages)
        now = datetime.now(timezone.utc)
        embed = discord.Embed(
            title="📢 频道主观点总结",
            description=summary,
            color=discord.Color.gold(),
            timestamp=now,
        )
        embed.set_footer(text=f"基于最近 {hours} 小时 · {owner_n} 条发言 · AI 生成")

        try:
            await interaction.channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("无法在本频道发消息，请检查 Bot 权限。", ephemeral=True)
            return
        except Exception:
            logger.exception("views command failed to post")
            await interaction.followup.send("发送失败，请稍后再试。", ephemeral=True)
            return

        from bot.utils import save_summary
        save_summary(
            summary_type="views",
            title="📢 频道主观点总结",
            content=summary,
            message_count=owner_n,
            timestamp=now.isoformat(),
        )
        await interaction.followup.send(
            f"✅ 已根据最近 {hours} 小时本服务器 {owner_n} 条发言，把观点总结发到本频道。\n{dm_note}",
            ephemeral=True,
        )

    # ── /satisfaction ────────────────────────────────────────────────────

    @app_commands.command(name="satisfaction", description="[Owner] 查看用户满意度统计")
    @app_commands.describe(days="统计天数 (默认30)")
    async def satisfaction_cmd(self, interaction: discord.Interaction, days: int = 30) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.feedback import satisfaction_stats, low_satisfaction_answers
        sat = satisfaction_stats(days)
        embed = discord.Embed(
            title=f"👍 用户满意度 (最近 {days} 天)",
            color=discord.Color.green() if sat["satisfaction_rate"] >= 80 else discord.Color.orange(),
        )
        embed.add_field(name="满意率", value=f"{sat['satisfaction_rate']}%", inline=True)
        embed.add_field(name="总评价", value=str(sat["total"]), inline=True)
        embed.add_field(name="👍", value=str(sat["positive"]), inline=True)
        embed.add_field(name="👎", value=str(sat["negative"]), inline=True)

        negatives = low_satisfaction_answers(5)
        if negatives:
            lines = [f"• {n['question'][:60]}" for n in negatives]
            embed.add_field(name="最近差评问题", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /add_ban_word ─────────────────────────────────────────────────────

    @app_commands.command(name="add_ban_word", description="[Owner] 添加禁止词到自动审核列表")
    @app_commands.describe(word="要禁止的词语或短语")
    async def add_ban_word_cmd(self, interaction: discord.Interaction, word: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        from bot.ban_words import add_ban_word
        ok = await add_ban_word(word)
        if ok:
            await interaction.followup.send(f"✅ 已添加禁止词：**{word}**", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ 该词已存在或为空：{word}", ephemeral=True)

    # ── /remove_ban_word ──────────────────────────────────────────────────

    @app_commands.command(name="remove_ban_word", description="[Owner] 从自动审核列表移除禁止词")
    @app_commands.describe(word="要移除的禁止词")
    async def remove_ban_word_cmd(self, interaction: discord.Interaction, word: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.ban_words import remove_ban_word
        ok = remove_ban_word(word)
        if ok:
            await interaction.response.send_message(f"✅ 已移除禁止词：**{word}**", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ 未找到禁止词：{word}", ephemeral=True)

    # ── /list_ban_words ───────────────────────────────────────────────────

    @app_commands.command(name="list_ban_words", description="[Owner] 查看所有禁止词")
    async def list_ban_words_cmd(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message("只有频道主可以使用此命令。", ephemeral=True)
            return
        from bot.ban_words import get_ban_words
        words = get_ban_words()
        if not words:
            await interaction.response.send_message("禁止词列表为空。使用 `/add_ban_word` 添加。", ephemeral=True)
            return
        lines = [f"{i+1}. {w}" for i, w in enumerate(words)]
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n..."
        embed = discord.Embed(
            title=f"🚫 禁止词列表 ({len(words)} 个)",
            description=text,
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
