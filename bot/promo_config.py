"""Promotion helper utilities for BigTreeSignal product promotion.

Centralises channel checks, CTA text generation, and frequency gating
so that promotion logic stays out of the core bot modules.
"""

import logging

import discord

from bot.config import (
    AUTO_REPLY_CTA_TEXT,
    CTA_FREQUENCY,
    FREE_TRIAL_ENABLED,
    FREE_TRIAL_URL,
    PROMO_CHANNEL_IDS,
    PROMO_ENABLED,
    SIGNAL_CTA_TEXT,
    SIGNAL_PRODUCT_NAME,
    SIGNAL_PRODUCT_URL,
)

logger = logging.getLogger(__name__)


def is_promo_channel(channel_id: int) -> bool:
    """Return True if *channel_id* is in the configured promotion channel list."""
    if not PROMO_ENABLED:
        return False
    if not PROMO_CHANNEL_IDS:
        return False
    return channel_id in PROMO_CHANNEL_IDS


def get_signal_cta_embed() -> discord.Embed:
    """Build an Embed used when a signal-type question is detected."""
    embed = discord.Embed(
        title=f"🌳 {SIGNAL_PRODUCT_NAME}",
        description=SIGNAL_CTA_TEXT,
        color=discord.Color.green(),
    )
    if SIGNAL_PRODUCT_URL:
        embed.add_field(
            name="📊 覆盖市场",
            value="美股 · ETF · 加密货币",
            inline=True,
        )
        embed.add_field(
            name="🔗 了解更多",
            value=f"[点击查看]({SIGNAL_PRODUCT_URL})",
            inline=True,
        )
    if FREE_TRIAL_ENABLED and FREE_TRIAL_URL:
        embed.add_field(
            name="🆓 免费试用",
            value=f"[开始试用]({FREE_TRIAL_URL})",
            inline=True,
        )
    return embed


def get_auto_reply_cta() -> str:
    """Return the CTA line to append to an auto-reply message."""
    cta = f"\n\n*💡 {AUTO_REPLY_CTA_TEXT}*"
    if SIGNAL_PRODUCT_URL:
        cta = f"\n\n*💡 [{AUTO_REPLY_CTA_TEXT}]({SIGNAL_PRODUCT_URL})*"
    return cta


def should_append_cta(counter: int) -> bool:
    """Return True if a CTA should be appended based on the rolling counter.

    Appends once every ``CTA_FREQUENCY`` auto-replies.  A frequency of 0 or
    negative disables the auto-reply CTA entirely.
    """
    if not PROMO_ENABLED:
        return False
    if CTA_FREQUENCY <= 0:
        return False
    return counter % CTA_FREQUENCY == 0


def get_welcome_embed(member: discord.Member) -> discord.Embed:
    """Build a welcome DM Embed for a newly joined member."""
    from bot.config import WELCOME_MESSAGE

    embed = discord.Embed(
        title=f"欢迎 {member.display_name}！🌳",
        description=WELCOME_MESSAGE,
        color=discord.Color.green(),
    )
    embed.add_field(
        name=f"📈 {SIGNAL_PRODUCT_NAME}",
        value=(
            "我们的信号产品覆盖美股、ETF、加密货币，帮你捕捉交易机会。"
        ),
        inline=False,
    )
    if SIGNAL_PRODUCT_URL:
        embed.add_field(
            name="🔗 了解更多",
            value=f"[点击查看]({SIGNAL_PRODUCT_URL})",
            inline=True,
        )
    if FREE_TRIAL_ENABLED and FREE_TRIAL_URL:
        embed.add_field(
            name="🆓 免费试用",
            value=f"[开始试用]({FREE_TRIAL_URL})",
            inline=True,
        )
    return embed


def get_signal_product_embed() -> discord.Embed:
    """Build a detailed product info Embed for the /signal slash command."""
    embed = discord.Embed(
        title=f"🌳 {SIGNAL_PRODUCT_NAME} 交易信号",
        description="专业交易信号服务，让你不再错过行情",
        color=discord.Color.green(),
    )
    embed.add_field(
        name="📊 覆盖市场",
        value="美股 · ETF · 加密货币",
        inline=True,
    )
    embed.add_field(
        name="⏰ 推送方式",
        value="Discord 实时推送",
        inline=True,
    )
    if SIGNAL_PRODUCT_URL:
        embed.add_field(
            name="🔗 订阅链接",
            value=f"[点击订阅]({SIGNAL_PRODUCT_URL})",
            inline=False,
        )
    if FREE_TRIAL_ENABLED and FREE_TRIAL_URL:
        embed.add_field(
            name="🆓 免费试用",
            value=f"[开始 免费试用]({FREE_TRIAL_URL})",
            inline=False,
        )
    return embed
