"""Auto-moderation — detect and delete spam, scam, and advertising messages.

Detection layers:
1. **Keyword patterns** — known spam / scam / ad phrases (Chinese + English).
2. **Ban words** — owner-configurable ban-word list (exact substring + semantic similarity).
3. **Excessive mentions** — mass-pinging (@everyone abuse or many user mentions).
4. **Link flooding** — too many URLs in a single message.
5. **Duplicate message spam** — same content posted repeatedly within a window.
6. **Invite link spam** — Discord invite links from non-exempt users.

When a message is flagged:
- It is **deleted** (requires ``Manage Messages`` permission).
- A log embed is sent to ``AUTO_MOD_LOG_CHANNEL_ID`` (if configured).
- The author may optionally be timed-out (future enhancement).

Configuration lives in ``bot/config.py`` — all tuneable via env vars.
"""

import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot.config import (
    AUTO_MOD_DUP_THRESHOLD,
    AUTO_MOD_DUP_WINDOW,
    AUTO_MOD_ENABLED,
    AUTO_MOD_EXEMPT_ROLE_IDS,
    AUTO_MOD_LOG_CHANNEL_ID,
    AUTO_MOD_MAX_LINKS,
    AUTO_MOD_MAX_MENTIONS,
    OWNER_USER_ID,
)

logger = logging.getLogger(__name__)

# ── Spam keyword patterns ──────────────────────────────────────────────────
# Chinese (simplified + traditional) and English patterns for common spam,
# scam, and advertising messages in stock / crypto / investment Discord servers.
_SPAM_KEYWORDS = re.compile(
    r"("
    # ── Chinese spam / scam / ads ──
    r"免费开放|免費開放|VIP群[组組]|加入我[们們]|点击链接|點擊連結|點擊鏈結|"
    r"名额有限|名額有限|全程指[导導]|立即加入|限时免费|限時免費|"
    r"私信领取|私信領取|加微信|加[Vv][Xx]|扫码加入|掃碼加入|"
    r"免费带[单單]|免費帶[单單]|稳赚不[赔賠]|穩賺不賠|保本保息|"
    r"日[赚賺]\d|月入\d|翻倍计划|翻倍計劃|保证盈利|保證盈利|"
    r"零风险|零風險|内幕消息|內幕消息|牛股推荐|牛股推薦|"
    r"股票配资|股票配資|期货配资|期貨配資|代操盘|代操盤|"
    r"杀猪盘|殺豬盤|资金盘|資金盤|传销|傳銷|"
    r"拉人头|拉人頭|下线|下線|返佣|返傭|回扣|"
    r"色情|赌博|賭博|博彩|棋牌|网赚|網賺|"
    r"刷单|刷單|兼职|兼職|日结|日結|在家[赚賺]|"
    r"贷款|貸款|信用卡套现|信用卡套現|洗钱|洗錢|"
    # ── English spam / scam ──
    r"guaranteed\s*profit|risk[\s-]*free|100%\s*return|"
    r"double\s*your\s*money|get\s*rich\s*quick|"
    r"send\s*me\s*dm|check\s*my\s*bio|link\s*in\s*bio|"
    r"airdrop\s*claim|claim\s*your|free\s*giveaway|"
    r"pump\s*and\s*dump|insider\s*info|"
    r"make\s*\$?\d+.*per\s*(day|week|month)|"
    r"crypto\s*investment\s*plan|forex\s*signal\s*free|"
    r"whatsapp\s*group|join\s*my\s*group"
    r")",
    re.IGNORECASE,
)

# Discord invite link pattern
_DISCORD_INVITE = re.compile(
    r"(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)",
    re.IGNORECASE,
)

# URL pattern for link-flooding detection
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+",
    re.IGNORECASE,
)

# External messaging platform links (often used in scams)
_EXTERNAL_PLATFORM_LINKS = re.compile(
    r"(t\.me/|telegram\.me/|wa\.me/|whatsapp\.com/|line\.me/|"
    r"bit\.ly/|tinyurl\.com/|goo\.gl/|短链接|短鏈接)",
    re.IGNORECASE,
)

# ── Duplicate message tracker ──────────────────────────────────────────────
# {user_id: [(timestamp, content_hash), ...]}
_recent_messages: dict[int, list[tuple[float, str]]] = defaultdict(list)
_MAX_TRACKED_USERS = 2000  # cap to prevent unbounded memory


def _clean_old_entries(user_id: int, now: float) -> None:
    """Remove entries older than the duplicate window."""
    cutoff = now - AUTO_MOD_DUP_WINDOW
    _recent_messages[user_id] = [
        (ts, h) for ts, h in _recent_messages[user_id] if ts > cutoff
    ]
    if not _recent_messages[user_id]:
        del _recent_messages[user_id]
    # Evict oldest users if tracker grows too large
    if len(_recent_messages) > _MAX_TRACKED_USERS:
        oldest_users = sorted(_recent_messages, key=lambda uid: _recent_messages[uid][0][0] if _recent_messages[uid] else 0)
        for uid in oldest_users[:len(_recent_messages) - _MAX_TRACKED_USERS]:
            del _recent_messages[uid]


def _check_duplicate(user_id: int, content: str) -> bool:
    """Return True if the user posted the same content too many times recently."""
    now = time.monotonic()
    _clean_old_entries(user_id, now)

    content_hash = content.strip().lower()
    _recent_messages[user_id].append((now, content_hash))

    count = sum(1 for _, h in _recent_messages[user_id] if h == content_hash)
    return count >= AUTO_MOD_DUP_THRESHOLD


# ── Detection functions ───────────────────────────────────────────────────

def check_message(message: discord.Message) -> str | None:
    """Check a message for spam/scam/ad patterns (synchronous checks only).

    Returns a reason string if flagged, or None if clean.
    For async checks (semantic ban-word similarity), use ``check_message_async``.
    """
    content = message.content or ""

    # 1. Keyword patterns
    m = _SPAM_KEYWORDS.search(content)
    if m:
        return f"spam keyword: {m.group()[:40]}"

    # 2. Ban words — exact substring match
    from bot.ban_words import check_exact
    exact = check_exact(content)
    if exact:
        return f"ban word: {exact}"

    # 3. External platform links (Telegram, WhatsApp, etc.)
    if _EXTERNAL_PLATFORM_LINKS.search(content):
        return "external platform link"

    # 4. Discord invite links
    if _DISCORD_INVITE.search(content):
        return "discord invite link"

    # 5. Excessive mentions
    total_mentions = len(message.mentions) + len(message.role_mentions)
    if message.mention_everyone:
        total_mentions += 1
    if total_mentions > AUTO_MOD_MAX_MENTIONS:
        return f"excessive mentions ({total_mentions})"

    # 6. Link flooding
    urls = _URL_PATTERN.findall(content)
    if len(urls) > AUTO_MOD_MAX_LINKS:
        return f"link flooding ({len(urls)} URLs)"

    # 7. Duplicate message spam
    if content.strip() and _check_duplicate(message.author.id, content):
        return f"duplicate spam ({AUTO_MOD_DUP_THRESHOLD}x in {AUTO_MOD_DUP_WINDOW}s)"

    return None


async def check_message_async(message: discord.Message) -> str | None:
    """Run async checks (semantic ban-word similarity).

    Call this *after* ``check_message`` returns None.
    """
    content = message.content or ""
    if not content.strip():
        return None

    from bot.ban_words import check_semantic
    result = await check_semantic(content)
    if result:
        word, score = result
        return f"ban word (semantic {score:.0%}): {word}"

    return None


def is_exempt(message: discord.Message) -> bool:
    """Return True if the message author is exempt from auto-mod."""
    # Owner is always exempt
    if message.author.id == OWNER_USER_ID:
        return True
    # Bots are exempt (we don't moderate other bots)
    if message.author.bot:
        return True
    # Check exempt roles
    if AUTO_MOD_EXEMPT_ROLE_IDS and isinstance(message.author, discord.Member):
        author_role_ids = {r.id for r in message.author.roles}
        if author_role_ids & set(AUTO_MOD_EXEMPT_ROLE_IDS):
            return True
    return False


# ── Cog ────────────────────────────────────────────────────────────────────

class AutoModCog(commands.Cog):
    """Listens for all messages and auto-deletes spam / scam / ads."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._log_channel: discord.TextChannel | None = None
        self._owner_user: discord.User | None = None

    async def _get_log_channel(self) -> discord.TextChannel | None:
        if self._log_channel is not None:
            return self._log_channel
        if AUTO_MOD_LOG_CHANNEL_ID:
            ch = self.bot.get_channel(AUTO_MOD_LOG_CHANNEL_ID)
            if isinstance(ch, discord.TextChannel):
                self._log_channel = ch
                return ch
        return None

    def _build_log_embed(self, message: discord.Message, reason: str) -> discord.Embed:
        """Build a log embed for a deleted message."""
        embed = discord.Embed(
            title="🛡️ Auto-Mod: Message Deleted",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=True)
        embed.add_field(name="Channel", value=f"<#{message.channel.id}>", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        content_preview = (message.content or "")[:500]
        if content_preview:
            safe = content_preview.replace("`", "\u200b`")
            embed.add_field(name="Content", value=f"```{safe}```", inline=False)
        return embed

    async def _log_action(
        self, message: discord.Message, reason: str
    ) -> None:
        """Send a log embed to the moderation log channel and DM the owner."""
        embed = self._build_log_embed(message, reason)

        # Send to log channel (if configured)
        log_ch = await self._get_log_channel()
        if log_ch is not None:
            try:
                await log_ch.send(embed=embed)
            except Exception as exc:
                logger.warning("Auto-mod: failed to send log to channel: %s", exc)

        # DM the owner
        await self._dm_owner(embed)

    async def _dm_owner(self, embed: discord.Embed) -> None:
        """Send an embed to the bot owner via DM."""
        if not OWNER_USER_ID:
            return
        try:
            if self._owner_user is None:
                self._owner_user = self.bot.get_user(OWNER_USER_ID) or await self.bot.fetch_user(OWNER_USER_ID)
            if self._owner_user:
                await self._owner_user.send(embed=embed)
        except discord.Forbidden:
            logger.debug("Auto-mod: owner DMs are closed, skipping DM notification")
        except Exception as exc:
            logger.warning("Auto-mod: failed to DM owner: %s", exc)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not AUTO_MOD_ENABLED:
            return

        # Skip exempt users
        if is_exempt(message):
            return

        # Skip DMs
        if message.guild is None:
            return

        reason = check_message(message)
        if reason is None:
            # Run async checks (semantic ban-word similarity)
            reason = await check_message_async(message)
        if reason is None:
            # Topic-restricted channel check (GPT classification)
            from bot.topic_guard import check_topic
            reason = await check_topic(message.channel.id, message.content or "")
        if reason is None:
            return

        # Attempt to delete
        try:
            await message.delete()
            logger.info(
                "Auto-mod: deleted message from %s (%d) in #%s — %s",
                message.author, message.author.id,
                getattr(message.channel, 'name', message.channel.id),
                reason,
            )
        except discord.Forbidden:
            logger.warning(
                "Auto-mod: no permission to delete message from %s in #%s",
                message.author,
                getattr(message.channel, 'name', message.channel.id),
            )
            return
        except discord.NotFound:
            # Already deleted
            return

        # Log to moderation channel
        await self._log_action(message, reason)
