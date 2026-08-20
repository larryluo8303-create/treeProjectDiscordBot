"""User testimonial collection, owner review, and forwarding to #user-wins.

Flow:
1. listener.py detects a testimonial-like message → calls collect_testimonial()
2. Owner receives a DM with Approve / Reject buttons
3. On Approve → message is forwarded to TESTIMONIAL_CHANNEL_ID
4. Data persisted in data/testimonials.json
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import discord

from bot.config import (
    OWNER_USER_ID,
    SIGNAL_PRODUCT_NAME,
    TESTIMONIAL_CHANNEL_ID,
)
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

TESTIMONIALS_FILE = data_path(os.getenv("TESTIMONIALS_FILE", "data/testimonials.json"))


# ── JSON persistence ─────────────────────────────────────────────────────────

def _load_testimonials() -> list[dict]:
    try:
        with open(TESTIMONIALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_testimonials(data: list[dict]) -> None:
    atomic_json_write(TESTIMONIALS_FILE, data, ensure_ascii=False, indent=2)


def get_approved_testimonials(limit: int = 5) -> list[dict]:
    """Return the most recent approved testimonials."""
    data = _load_testimonials()
    approved = [t for t in data if t.get("status") == "approved"]
    return approved[-limit:]


# ── Collection ───────────────────────────────────────────────────────────────

async def collect_testimonial(
    bot: discord.Client,
    message: discord.Message,
) -> None:
    """Store a potential testimonial and DM the owner for approval."""
    data = _load_testimonials()

    # Deduplicate by message ID
    if any(t.get("message_id") == str(message.id) for t in data):
        return

    testimonial = {
        "id": f"test_{uuid.uuid4().hex[:8]}",
        "message_id": str(message.id),
        "channel_id": str(message.channel.id),
        "author_id": str(message.author.id),
        "author_name": message.author.display_name,
        "content": message.content[:500],
        "timestamp": message.created_at.isoformat(),
        "status": "pending",
        "jump_url": message.jump_url if hasattr(message, "jump_url") else "",
    }
    data.append(testimonial)
    _save_testimonials(data)

    logger.info("Collected testimonial %s from %s", testimonial["id"], message.author)

    # DM owner for review
    try:
        owner = await bot.fetch_user(OWNER_USER_ID)
        if not owner:
            return

        embed = discord.Embed(
            title="🌟 新用户见证待审核",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="频道",
            value=f"<#{message.channel.id}>",
            inline=True,
        )
        embed.add_field(
            name="用户",
            value=f"{message.author.display_name} ({message.author})",
            inline=True,
        )
        embed.add_field(
            name="内容",
            value=message.content[:1000] or "(无文字)",
            inline=False,
        )
        if hasattr(message, "jump_url"):
            embed.add_field(
                name="链接",
                value=f"[跳转到消息]({message.jump_url})",
                inline=False,
            )

        view = TestimonialReviewView(
            bot=bot,
            testimonial_id=testimonial["id"],
            original_message=message,
        )
        await owner.send(embed=embed, view=view)
        logger.info("Sent testimonial review DM for %s", testimonial["id"])

    except discord.Forbidden:
        logger.error("Cannot DM owner for testimonial review — DMs may be disabled")
    except Exception as exc:
        logger.error("Failed to send testimonial review DM: %s", exc)


# ── Review UI ────────────────────────────────────────────────────────────────

class TestimonialReviewView(discord.ui.View):
    """Approve / Reject buttons for testimonial review."""

    def __init__(
        self,
        bot: discord.Client,
        testimonial_id: str,
        original_message: discord.Message,
    ):
        super().__init__(timeout=86400)  # 24 hours
        self.bot = bot
        self.testimonial_id = testimonial_id
        self.original_message = original_message
        self.handled = False

    @discord.ui.button(label="✅ 通过", style=discord.ButtonStyle.success)
    async def approve(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.handled:
            await interaction.response.send_message("已处理。", ephemeral=True)
            return

        self.handled = True

        # Update status in JSON
        data = _load_testimonials()
        for t in data:
            if t["id"] == self.testimonial_id:
                t["status"] = "approved"
                t["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                break
        _save_testimonials(data)

        # Forward to #user-wins channel
        forwarded = False
        if TESTIMONIAL_CHANNEL_ID:
            ch = self.bot.get_channel(TESTIMONIAL_CHANNEL_ID)
            if ch is None:
                try:
                    ch = await self.bot.fetch_channel(TESTIMONIAL_CHANNEL_ID)
                except Exception:
                    ch = None

            if ch:
                embed = discord.Embed(
                    title="🌟 用户好评",
                    description=self.original_message.content[:1500],
                    color=discord.Color.gold(),
                )
                embed.set_author(
                    name=self.original_message.author.display_name,
                    icon_url=(
                        self.original_message.author.display_avatar.url
                        if self.original_message.author.display_avatar
                        else None
                    ),
                )
                embed.timestamp = self.original_message.created_at
                embed.set_footer(text=f"🌳 {SIGNAL_PRODUCT_NAME}")

                if hasattr(self.original_message, "jump_url"):
                    embed.add_field(
                        name="原始消息",
                        value=f"[查看原文]({self.original_message.jump_url})",
                        inline=False,
                    )
                try:
                    await ch.send(embed=embed)
                    forwarded = True
                    logger.info("Forwarded testimonial %s to #user-wins channel",
                                self.testimonial_id)
                except Exception as exc:
                    logger.warning("Failed to forward testimonial: %s", exc)

        status = "已通过并转发到见证频道" if forwarded else "已通过（未配置见证频道）"
        await interaction.response.edit_message(
            content=f"✅ **{status}**",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="❌ 拒绝", style=discord.ButtonStyle.danger)
    async def reject(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.handled:
            await interaction.response.send_message("已处理。", ephemeral=True)
            return

        self.handled = True

        # Update status in JSON
        data = _load_testimonials()
        for t in data:
            if t["id"] == self.testimonial_id:
                t["status"] = "rejected"
                t["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                break
        _save_testimonials(data)

        await interaction.response.edit_message(
            content="❌ **见证已拒绝。**",
            embed=None,
            view=None,
        )
        logger.info("Rejected testimonial %s", self.testimonial_id)
