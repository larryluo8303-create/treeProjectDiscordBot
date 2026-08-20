"""Welcome DM for new members, then schedule a 24–72h conversion drip.

Step 1 is sent immediately. Later steps (value proof, product CTA, reminder)
are persisted in ``data/welcome_drip.json`` so they survive bot restarts.
"""

from __future__ import annotations

import logging

import discord

from bot.acquisition import build_cta_view, record_funnel, schedule_welcome_drip
from bot.config import SIGNAL_PRODUCT_NAME, WELCOME_MESSAGE

logger = logging.getLogger(__name__)


def _build_welcome_view(guild: discord.Guild) -> discord.ui.View | None:
    """CTA row plus optional 领取通知 / 取消订阅 on the next row."""
    from bot.role_dm import attach_welcome_notify_buttons

    view = build_cta_view() or discord.ui.View(timeout=None)
    attach_welcome_notify_buttons(view, guild, row=1)
    return view if view.children else None


async def run_welcome_flow(member: discord.Member) -> None:
    """Send the immediate welcome DM and enqueue drip jobs."""
    description = WELCOME_MESSAGE or "欢迎来到我们的社群！"
    description += (
        "\n\n建议先看这些：\n"
        "• `/faq` 常见问题\n"
        "• `/ask` 向 AI 助手提问\n"
        f"• `/signal` 了解 {SIGNAL_PRODUCT_NAME}"
    )
    from bot.role_dm import default_notify_role_id

    if default_notify_role_id():
        description += (
            "\n\n想在优惠/活动时收到私信，点下面的「领取通知」。随时可取消。"
        )
    embed = discord.Embed(
        title=f"👋 欢迎加入 {member.guild.name}！",
        description=description,
        color=discord.Color.green(),
    )
    embed.set_footer(text="有问题随时在频道里提问")
    view = _build_welcome_view(member.guild)

    try:
        await member.send(embed=embed, view=view)
        record_funnel("welcome_dm_ok")
        logger.info("Welcome step 1 sent to %s", member)
    except discord.Forbidden:
        record_funnel("welcome_dm_blocked")
        logger.info("Cannot DM member %s — DMs disabled", member)
        return
    except Exception as exc:
        record_funnel("welcome_dm_blocked")
        logger.warning("Welcome step 1 failed for %s: %s", member, exc)
        return

    schedule_welcome_drip(member.id, member.guild.id)
