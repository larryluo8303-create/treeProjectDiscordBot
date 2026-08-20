"""Discord message listener — on_message handler, filtering, rate limiting, queue."""

import asyncio
import json
import logging
import os
import time
from datetime import timedelta

import re

import chromadb
import discord
import openai
from discord.ext import commands

from bot.config import (
    AUTO_LANG_DETECT,
    CLARIFICATION_CONFIDENCE_MAX,
    CONVERSATION_MEMORY_SIZE,
    CONVERSATION_MEMORY_TTL,
    EMBEDDING_MODEL,
    EXCLUDED_CHANNEL_IDS,
    FEEDBACK_ENABLED,
    FEATURE_CLARIFICATION_CANARY_CHANNEL_IDS,
    FEATURE_CLARIFICATION_FOLLOWUP,
    FEATURE_FEEDBACK_LEARNING,
    FEATURE_FEEDBACK_LEARNING_CANARY_CHANNEL_IDS,
    FEATURE_LANG_DETECT,
    FEATURE_LANG_DETECT_CANARY_CHANNEL_IDS,
    FEATURE_SAFETY_GUARDRAILS,
    FEATURE_SAFETY_GUARDRAILS_CANARY_CHANNEL_IDS,
    FEATURE_SESSION_SUMMARY,
    FEATURE_SESSION_SUMMARY_CANARY_CHANNEL_IDS,
    GLOBAL_MAX_PER_MINUTE,
    GUARDRAIL_DISCLAIMER,
    GUARDRAIL_MODE,
    INTENT_CONVERT_ENABLED,
    KEYWORD_ALERT_ENABLED,
    OFFLINE_BACKFILL_ENABLED,
    OFFLINE_BACKFILL_LOOKBACK_HOURS,
    OFFLINE_BACKFILL_MAX_PER_CHANNEL,
    OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES,
    OFFLINE_LAST_SEEN_FILE,
    OWNER_USER_ID,
    PROMO_CHANNEL_IDS,
    PROMO_ENABLED,
    PROMO_SOURCE_CHANNEL_ID,
    RESPOND_MODE,
    TARGET_CHANNEL_IDS,
    TESTIMONIAL_CHANNEL_ID,
    TESTIMONIAL_DETECTION_ENABLED,
    THREAD_AUTO_REPLY,
    THREAD_CONTEXT_MESSAGES,
    USER_COOLDOWN_SECONDS,
    VIP_ROLE_IDS,
    WELCOME_FLOW_ENABLED,
    SESSION_SUMMARY_KEEP_RECENT,
    SESSION_SUMMARY_TRIGGER_MESSAGES,
    get_locale,
)
from bot.confidence import is_signal_query, route_answer
from bot.feature_flags import is_feature_enabled_for_channel
from bot.promo_config import (
    get_auto_reply_cta,
    get_signal_cta_embed,
    get_signal_product_embed,
    get_welcome_embed,
    is_promo_channel,
    should_append_cta,
)
from bot.auto_mod import _DISCORD_INVITE, _EXTERNAL_PLATFORM_LINKS, _SPAM_KEYWORDS
from bot.rag import analyze_image, retrieve_context, run_rag_pipeline
from bot.review import notify_owner_auto_reply, send_for_review
from bot.stats import bot_stats

logger = logging.getLogger(__name__)

DISCORD_MAX_LENGTH = 2000

# Discord voice-note limits before Whisper (avoid queue stalls / cost spikes).
_MAX_VOICE_BYTES = 2 * 1024 * 1024  # 2 MB
_MAX_VOICE_SECONDS = 90.0
_VOICE_MEMORY_CHARS = 500

# Regex matching a single Unicode emoji character (covers Emoticons, Dingbats,
# Symbols, Transport/Map, Supplemental, Flags, and variation selectors / ZWJ).
_EMOJI_RE = re.compile(
    r"[\U0001F600-\U0001F64F"   # Emoticons
    r"\U0001F300-\U0001F5FF"    # Misc Symbols & Pictographs
    r"\U0001F680-\U0001F6FF"    # Transport & Map
    r"\U0001F1E0-\U0001F1FF"    # Flags (regional indicator)
    r"\U0001F900-\U0001F9FF"    # Supplemental Symbols & Pictographs
    r"\U0001FA00-\U0001FA6F"    # Chess, Extended-A
    r"\U0001FA70-\U0001FAFF"    # Extended-A cont.
    r"\U00002702-\U000027B0"    # Dingbats
    r"\U000024C2-\U0000257F"    # Enclosed Alphanumerics
    r"\U0000FE00-\U0000FE0F"    # Variation Selectors
    r"\U0000200D"               # ZWJ
    r"\U000020E3"               # Combining Enclosing Keycap
    r"\U00002600-\U000026FF"    # Misc Symbols
    r"\U0000231A-\U0000231B"    # Watch, Hourglass
    r"\U00002934-\U00002935"    # Arrows
    r"\U000025AA-\U000025FE"    # Geometric Shapes
    r"\U00002B05-\U00002B55"    # Arrows & shapes
    r"\U0000203C-\U00003299"    # CJK symbols (limited subset used as emoji)
    r"]"
)


def _is_pure_emoji(text: str) -> bool:
    """Return True if *text* consists entirely of emoji (and whitespace)."""
    stripped = text.strip()
    if not stripped:
        return False
    # Remove all emoji characters and whitespace — if nothing remains, it's pure emoji.
    remaining = _EMOJI_RE.sub("", stripped)
    remaining = remaining.replace(" ", "").replace("\n", "").replace("\t", "")
    return len(remaining) == 0


class MessageListener(commands.Cog):
    """Cog that listens for messages, runs the RAG pipeline, and responds."""

    def __init__(
        self,
        bot: commands.Bot,
        collection: chromadb.Collection,
        openai_client: openai.AsyncOpenAI,
    ):
        self.bot = bot
        self.collection = collection
        self.openai_client = openai_client
        self._user_cooldowns: dict[int, list] = {}  # {user_id: [tokens, last_refill_time]}
        self._global_tokens: float = float(GLOBAL_MAX_PER_MINUTE)
        self._global_last_refill: float = time.time()
        self._queue: asyncio.Queue[discord.Message] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        # Per-channel conversation memory: {channel_id: [(timestamp, role, text), ...]}
        self._channel_memory: dict[int, list[tuple[float, str, str]]] = {}
        # Per-channel last processed message id (for offline backfill resume)
        self._last_seen: dict[int, int] = self._load_last_seen()
        self._backfill_lock = asyncio.Lock()
        # Rolling counter for CTA frequency gating (promotion)
        self._auto_reply_counter: int = 0
        # Periodic save state
        self._last_seen_dirty: bool = False
        self._save_periodic_task: asyncio.Task | None = None
        self._shutting_down: bool = False

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bot is ready — starting message queue worker")
        # Guard against duplicate workers on Discord reconnect (on_ready can fire multiple times)
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue())
        if self._save_periodic_task is None or self._save_periodic_task.done():
            self._save_periodic_task = asyncio.create_task(self._periodic_save_loop())
        await bot_stats.start_periodic_save()
        # Scan for unanswered questions that arrived while the bot was offline
        if OFFLINE_BACKFILL_ENABLED:
            asyncio.create_task(self._backfill_offline_messages())

    async def cog_unload(self):
        self._shutting_down = True
        # Cancel periodic save task
        if self._save_periodic_task is not None:
            self._save_periodic_task.cancel()
            self._save_periodic_task = None
        # Cancel queue worker and flush remaining state
        if self._worker_task is not None:
            self._worker_task.cancel()
            self._worker_task = None
        # Final save on shutdown
        if self._last_seen_dirty:
            self._save_last_seen()
            self._last_seen_dirty = False
        await bot_stats.stop()

    # ── Filtering ────────────────────────────────────────────────────────────

    # Spam / advertising keywords — delegates to auto_mod's comprehensive patterns
    _SPAM_PATTERNS = _SPAM_KEYWORDS

    # Courtesy / gratitude messages that don't need a reply
    _COURTESY_PATTERNS = re.compile(
        r"^[\s]*(谢谢|謝謝|感谢|感謝|thanks|thank you|thx|ty|多谢|多謝|"
        r"感恩|辛苦了|辛苦啦|太感谢|太感謝|非常感谢|非常感謝|"
        r"谢谢大佬|謝謝大佬|感谢分享|感謝分享|谢谢老师|謝謝老師|"
        r"学到了|學到了|受教了|收到|明白了|懂了|了解了|好的谢谢|好的謝謝|"
        r"谢谢回复|謝謝回覆|感谢回复|感謝回覆|👍|🙏|❤️|💯)[\s!！。.~～]*$",
        re.IGNORECASE,
    )

    # User testimonial / profit sharing patterns — used to detect positive feedback
    # for automatic testimonial collection.
    _TESTIMONIAL_PATTERNS = re.compile(
        r"(赚了|賺了|盈利|翻倍|大赚|大賺|跟单|跟單|跟信号|跟信號|信号准|信號準|"
        r"赚到|賺到|出金|回本|赚钱|賺錢|收益不错|收益不錯|"
        r"profit|gains|made money|signal works|great signal|good signal)",
        re.IGNORECASE,
    )

    # Question / help-request markers — used to gate auto-reply so the bot doesn't
    # interrupt regular chatter and sharing.
    _QUESTION_PATTERNS = re.compile(
        r"[?？]|"
        r"(怎么|怎样|怎麼|如何|"
        r"为什么|為什麼|为啥|為啥|为何|為何|"
        r"是不是|是否|能不能|能否|可不可以|可以吗|可以嗎|行不行|行吗|行嗎|"
        r"有没有|有沒有|什么|什麼|啥|"
        r"哪个|哪個|哪些|哪里|哪裡|哪儿|哪兒|哪天|哪种|哪種|"
        r"多少|多久|多长|多長|多远|多遠|多高|多低|多大|多深|"
        r"几点|幾點|几个|幾個|几时|幾時|"
        r"请问|請問|请教|請教|求助|求教|教教|想问|想問|想请教|想請教|"
        r"问一下|問一下|问下|問下|问个|問個|咨询|諮詢|"
        r"求分析|求看|帮看|幫看|帮分析|幫分析|帮我看|幫我看|"
        r"对吗|對嗎|对不对|對不對|是吗|是嗎|懂吗|懂嗎|"
        r"吗|嗎)",
        re.IGNORECASE,
    )

    @staticmethod
    def _is_thread(channel: discord.abc.Messageable) -> bool:
        """Return True if *channel* is a Thread."""
        return isinstance(channel, discord.Thread)

    @staticmethod
    def _get_parent_channel_id(channel: discord.abc.Messageable) -> int:
        """Return the parent channel ID if *channel* is a thread, else the channel's own ID."""
        if isinstance(channel, discord.Thread):
            return channel.parent_id or channel.id
        return channel.id

    def _bot_is_mentioned(self, message: discord.Message) -> bool:
        """True if the bot user is @mentioned in the message."""
        bot_user = self.bot.user
        return bot_user is not None and bot_user in message.mentions

    def _should_skip(self, message: discord.Message) -> bool:
        # Ignore bots (including self)
        if message.author.bot:
            logger.info("跳过: 机器人消息 (author=%s)", message.author)
            return True
        # Ignore owner messages — unless the owner explicitly @mentions the bot
        if message.author.id == OWNER_USER_ID and not self._bot_is_mentioned(message):
            logger.info("跳过: 频道主自己的消息 (author=%s)", message.author)
            return True
        # Ignore excluded channels
        if EXCLUDED_CHANNEL_IDS:
            effective_id = self._get_parent_channel_id(message.channel)
            if effective_id in EXCLUDED_CHANNEL_IDS or message.channel.id in EXCLUDED_CHANNEL_IDS:
                logger.info("跳过: 频道在排除列表 (channel_id=%s)", message.channel.id)
                return True
        # Ignore channels not in target list (threads are accepted if parent is a target)
        if TARGET_CHANNEL_IDS:
            effective_id = self._get_parent_channel_id(message.channel)
            is_thread = self._is_thread(message.channel)
            if effective_id not in TARGET_CHANNEL_IDS:
                logger.info("跳过: 频道不在监听列表 (channel_id=%s, 监听=%s)", message.channel.id, TARGET_CHANNEL_IDS)
                return True
            if is_thread and not THREAD_AUTO_REPLY:
                logger.info("跳过: Thread回复已禁用 (thread_id=%s)", message.channel.id)
                return True
        # Ignore empty messages (no text AND no image/voice attachments)
        has_text = message.content and message.content.strip()
        has_image = any(
            a.content_type and a.content_type.startswith("image/")
            for a in message.attachments
        )
        has_voice = self._get_voice_attachment(message) is not None
        if not has_text and not has_image and not has_voice:
            logger.info("跳过: 空消息 (author=%s)", message.author)
            return True
        # Ignore spam / advertising
        if has_text and (
            self._SPAM_PATTERNS.search(message.content)
            or _EXTERNAL_PLATFORM_LINKS.search(message.content)
            or _DISCORD_INVITE.search(message.content)
        ):
            logger.info("跳过: 疑似垃圾广告 (author=%s, content=%s)",
                        message.author, message.content[:80])
            return True
        # Ignore courtesy / gratitude messages (no need to reply "不客气")
        if has_text and self._COURTESY_PATTERNS.match(message.content.strip()):
            logger.info("跳过: 客气/感谢消息无需回复 (author=%s, content=%s)",
                        message.author, message.content[:80])
            return True
        # Intent gate: skip pure chatter / sharing unless the user is asking the bot
        if RESPOND_MODE != "all" and not self._is_response_warranted(
            message, has_image, has_voice=has_voice,
        ):
            logger.info("跳过: 非提问/闲聊消息 (mode=%s, author=%s, content=%s)",
                        RESPOND_MODE, message.author, (message.content or "")[:80])
            return True
        return False

    def _is_response_warranted(
        self,
        message: discord.Message,
        has_image: bool,
        *,
        has_voice: bool = False,
    ) -> bool:
        """Decide if a message looks like it actually wants a bot reply.

        Always responds to: image/voice attachments, @mentions of the bot, replies to
        the bot's own messages. In the default 'questions' mode, also responds
        when the text contains question/help-request markers.
        """
        # Images / voice notes are almost always analysis or question requests
        if has_image or has_voice:
            return True
        # Explicit @mention of the bot user
        bot_user = self.bot.user
        if bot_user is not None and bot_user in message.mentions:
            return True
        # Reply to one of the bot's own messages (follow-up question)
        ref = message.reference
        resolved = getattr(ref, "resolved", None) if ref else None
        if (
            bot_user is not None
            and isinstance(resolved, discord.Message)
            and resolved.author.id == bot_user.id
        ):
            return True
        if RESPOND_MODE == "mention_only":
            return False
        # Question / help-request heuristic
        text = (message.content or "").strip()
        if text and self._QUESTION_PATTERNS.search(text):
            return True
        return False

    def _is_rate_limited(self, user_id: int) -> bool:
        now = time.time()

        # Per-user token bucket (1 token per USER_COOLDOWN_SECONDS, burst=1)
        user_bucket = self._user_cooldowns.get(user_id)
        if user_bucket is None:
            # (tokens, last_refill_time)
            self._user_cooldowns[user_id] = [1.0, now]
            user_bucket = self._user_cooldowns[user_id]
        else:
            elapsed = now - user_bucket[1]
            refill = elapsed / USER_COOLDOWN_SECONDS
            user_bucket[0] = min(1.0, user_bucket[0] + refill)
            user_bucket[1] = now

        if user_bucket[0] < 1.0:
            logger.info("跳过: 用户速率限制 (user=%d, %.1f s until token)", user_id,
                         (1.0 - user_bucket[0]) * USER_COOLDOWN_SECONDS)
            return True

        # Global token bucket (GLOBAL_MAX_PER_MINUTE tokens, refill rate = GLOBAL_MAX_PER_MINUTE/60 per sec)
        elapsed_global = now - self._global_last_refill
        refill_rate = GLOBAL_MAX_PER_MINUTE / 60.0
        self._global_tokens = min(
            float(GLOBAL_MAX_PER_MINUTE),
            self._global_tokens + elapsed_global * refill_rate,
        )
        self._global_last_refill = now

        if self._global_tokens < 1.0:
            logger.info("跳过: 全局速率限制 (tokens=%.2f)", self._global_tokens)
            return True

        return False

    def _record_reply(self, user_id: int) -> None:
        # Consume one token from each bucket
        user_bucket = self._user_cooldowns.get(user_id)
        if user_bucket is not None:
            user_bucket[0] = max(0.0, user_bucket[0] - 1.0)
        self._global_tokens = max(0.0, self._global_tokens - 1.0)

    # ── Conversation memory ──────────────────────────────────────────────────

    def _add_to_memory(self, channel_id: int, role: str, text: str) -> None:
        """Add a message to the channel's conversation memory."""
        now = time.time()
        if channel_id not in self._channel_memory:
            self._channel_memory[channel_id] = []

        buf = self._channel_memory[channel_id]
        buf.append((now, role, text[:500]))  # cap per-message length

        # Evict old messages (beyond TTL or max size)
        cutoff = now - CONVERSATION_MEMORY_TTL
        buf[:] = [(ts, r, t) for ts, r, t in buf if ts > cutoff]
        if len(buf) > CONVERSATION_MEMORY_SIZE:
            buf[:] = buf[-CONVERSATION_MEMORY_SIZE:]

        # Compress older turns into a lightweight session summary when enabled.
        # Guard: skip if buffer already contains a summary entry to avoid
        # recursively re-compressing previous summaries.
        has_summary = any(r == "summary" for _, r, _ in buf)
        if (
            not has_summary
            and is_feature_enabled_for_channel(
                FEATURE_SESSION_SUMMARY,
                FEATURE_SESSION_SUMMARY_CANARY_CHANNEL_IDS,
                channel_id,
            )
            and len(buf) >= SESSION_SUMMARY_TRIGGER_MESSAGES
        ):
            from bot.session_summary import summarize_memory_entries
            recent = buf[-SESSION_SUMMARY_KEEP_RECENT:]
            older = buf[:-SESSION_SUMMARY_KEEP_RECENT]
            if older:
                summary = summarize_memory_entries(older)
                if summary:
                    buf[:] = [(now, "summary", summary)] + recent

        # Opportunistically evict stale channels so the dict doesn't grow unbounded
        if len(self._channel_memory) > 50:
            stale = [
                cid for cid, b in self._channel_memory.items()
                if not b or b[-1][0] < cutoff
            ]
            for cid in stale:
                del self._channel_memory[cid]

    def _get_memory(self, channel_id: int) -> list[tuple[str, str]]:
        """Get recent conversation history for a channel as [(role, text), ...]."""
        if channel_id not in self._channel_memory:
            return []
        now = time.time()
        cutoff = now - CONVERSATION_MEMORY_TTL
        buf = self._channel_memory[channel_id]
        return [(r, t) for ts, r, t in buf if ts > cutoff]

    def _format_memory(self, channel_id: int) -> str:
        """Format conversation memory into a string for the prompt."""
        history = self._get_memory(channel_id)
        if not history:
            return ""
        lines = []
        user_label = get_locale("conversation_user")
        bot_label = get_locale("conversation_bot")
        for role, text in history:
            if role == "user":
                lines.append(f"{user_label}: {text}")
            elif role == "summary":
                lines.append(text)
            else:
                lines.append(f"{bot_label}: {text}")
        return get_locale("conversation_header") + "\n".join(lines) + "\n\n"

    # ── Thread context ────────────────────────────────────────────────────────

    async def _fetch_thread_context(self, thread: discord.Thread) -> str:
        """Fetch recent messages from a thread and format as conversation history.

        This supplements the per-channel conversation memory with the full
        thread history so the bot can give coherent follow-up answers.
        """
        try:
            messages: list[discord.Message] = []
            async for msg in thread.history(limit=THREAD_CONTEXT_MESSAGES, oldest_first=True):
                messages.append(msg)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Failed to fetch thread history for %s: %s", thread.id, exc)
            return ""

        if not messages:
            return ""

        bot_id = self.bot.user.id if self.bot.user else 0
        user_label = get_locale("conversation_user")
        bot_label = get_locale("conversation_bot")
        lines: list[str] = []
        for msg in messages:
            if msg.author.bot and msg.author.id == bot_id:
                text = (msg.content or "")[:500]
                if text:
                    lines.append(f"{bot_label}: {text}")
            elif not msg.author.bot:
                text = (msg.content or "")[:500]
                if text:
                    label = user_label if msg.author.id != OWNER_USER_ID else bot_label
                    lines.append(f"{label}: {text}")

        if not lines:
            return ""
        return get_locale("conversation_header") + "\n".join(lines) + "\n\n"

    # ── Event handler ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if isinstance(message.channel, (discord.DMChannel, discord.GroupChannel)):
            from bot.views_summary import remember_owner_private_channel
            remember_owner_private_channel(message)

        # Track latest message id seen in each watched channel for offline backfill resume.
        effective_channel = self._get_parent_channel_id(message.channel)
        if not TARGET_CHANNEL_IDS or effective_channel in TARGET_CHANNEL_IDS:
            if message.id > self._last_seen.get(effective_channel, 0):
                self._last_seen[effective_channel] = message.id
                self._last_seen_dirty = True

        # Auto-learn from owner's new posts — but if the owner @mentions the bot,
        # treat it as a query (skip learning, fall through to the normal reply path).
        # Skip promo source channel to avoid learning promo content into KB.
        if (
            not message.author.bot
            and message.author.id == OWNER_USER_ID
            and (not TARGET_CHANNEL_IDS or effective_channel in TARGET_CHANNEL_IDS)
            and message.content
            and message.content.strip()
            and not self._bot_is_mentioned(message)
            and message.channel.id != PROMO_SOURCE_CHANNEL_ID
        ):
            logger.info("自动学习: 检测到频道主消息 (id=%s, channel=%s, len=%d)",
                        message.id, message.channel.id, len(message.content))
            asyncio.create_task(self._learn_owner_message(message))
            return
        elif (
            not message.author.bot
            and message.author.id == OWNER_USER_ID
            and not self._bot_is_mentioned(message)
        ):
            # Check for voice/audio attachments from owner (even without text)
            if (
                self._get_voice_attachment(message) is not None
                and (not TARGET_CHANNEL_IDS or effective_channel in TARGET_CHANNEL_IDS)
            ):
                logger.info("自动学习: 检测到频道主语音消息 (id=%s, channel=%s)",
                            message.id, message.channel.id)
                asyncio.create_task(self._handle_owner_voice_message(message))
                return
            logger.info("跳过学习: 频道主消息不符合条件 (channel=%s, target=%s, content=%r)",
                        message.channel.id, TARGET_CHANNEL_IDS, bool(message.content))

        # ── Testimonial detection (before skip check) ──
        if (
            TESTIMONIAL_DETECTION_ENABLED
            and not message.author.bot
            and message.author.id != OWNER_USER_ID
            and message.content
            and self._TESTIMONIAL_PATTERNS.search(message.content)
            and is_promo_channel(message.channel.id)
        ):
            asyncio.create_task(self._handle_testimonial(message))

        # ── Keyword alert monitoring ──
        if (
            KEYWORD_ALERT_ENABLED
            and not message.author.bot
            and message.content
        ):
            from bot.keyword_alert import check_message
            matched = check_message(message.content)
            if matched:
                asyncio.create_task(self._send_keyword_alert(message, matched))

        if self._should_skip(message):
            return
        # VIP role bypass for rate limiting
        is_vip = self._is_vip(message.author)
        if not is_vip and self._is_rate_limited(message.author.id):
            return
        await self._queue.put(message)

    async def _learn_owner_message(self, message: discord.Message) -> None:
        """Embed and store the owner's new message into ChromaDB."""
        text = message.content.strip()

        # Skip trivial messages (too short, pure emoji, pure URL)
        if len(text) < 10:
            logger.info("自动学习: 跳过太短的消息 (id=%s, len=%d)", message.id, len(text))
            return
        if _is_pure_emoji(text):
            logger.info("自动学习: 跳过纯emoji消息 (id=%s)", message.id)
            return

        # If this is a reply to someone's question, store as Q&A pair for better retrieval
        qa_text = text
        if message.reference and message.reference.message_id:
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
                if ref_msg.content and ref_msg.content.strip() and ref_msg.author.id != OWNER_USER_ID:
                    qa_text = f"Q: {ref_msg.content.strip()}\nA: {text}"
            except Exception:
                pass  # reference message may be deleted

        doc_id = f"live_{message.id}"

        try:
            # Check if already stored
            existing = await self.collection.get(ids=[doc_id], include=[])
            if existing["ids"]:
                return  # already ingested

            try:
                response = await self.openai_client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=[qa_text],
                )
            except (openai.APITimeoutError, openai.APIConnectionError) as first_err:
                logger.warning("Embedding API error (%s) for message %s — retrying once",
                               type(first_err).__name__, message.id)
                response = await self.openai_client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=[qa_text],
                )
            embedding = response.data[0].embedding

            await self.collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[qa_text],
                metadatas=[{
                    "type": "qa_pair" if qa_text != text else "owner_post",
                    "source": "discord_live",
                    "channel_id": str(message.channel.id),
                    "message_id": str(message.id),
                    "author_id": str(message.author.id),
                    "timestamp": message.created_at.isoformat(),
                }],
            )
            logger.info("Auto-learned owner message %s (%d chars, type=%s)",
                        message.id, len(qa_text),
                        "qa_pair" if qa_text != text else "owner_post")
        except Exception as exc:
            logger.warning("Failed to auto-learn message %s: %s", message.id, exc)

    # ── Voice message helpers ───────────────────────────────────────────────

    @staticmethod
    def _get_voice_attachment(message: discord.Message) -> discord.Attachment | None:
        """Return a Discord voice-note attachment only (not arbitrary audio files)."""
        for att in message.attachments:
            # Preferred: discord.py marks voice messages via duration + waveform.
            is_voice = getattr(att, "is_voice_message", None)
            if callable(is_voice) and is_voice():
                return att
            # Fallback for partial/cached payloads: Discord names them voice-message.*
            name = (att.filename or "").lower()
            ct = (att.content_type or "").lower()
            if name.startswith("voice-message") and (
                ct.startswith("audio/") or name.endswith((".ogg", ".mp3", ".m4a", ".wav", ".webm"))
            ):
                return att
        return None

    @staticmethod
    def _voice_reject_reason(voice_att: discord.Attachment) -> str | None:
        """Return a user-facing reject reason if the voice note is too large/long."""
        size = getattr(voice_att, "size", None) or 0
        if size > _MAX_VOICE_BYTES:
            return "语音文件太大，请改成文字提问，或发更短的语音（约 90 秒内）。"
        duration = getattr(voice_att, "duration", None)
        if duration is not None and float(duration) > _MAX_VOICE_SECONDS:
            return "语音太长，请改成文字提问，或发 90 秒以内的语音。"
        return None

    def _voice_transcript_wants_reply(self, message: discord.Message, transcript: str) -> bool:
        """After Whisper, decide if a voice-only note still needs a bot reply."""
        text = (transcript or "").strip()
        if not text:
            return False
        if self._bot_is_mentioned(message):
            return True
        ref = message.reference
        resolved = getattr(ref, "resolved", None) if ref else None
        bot_user = self.bot.user
        if (
            bot_user is not None
            and isinstance(resolved, discord.Message)
            and resolved.author.id == bot_user.id
        ):
            return True
        if self._COURTESY_PATTERNS.match(text):
            return False
        if RESPOND_MODE == "all":
            return True
        if RESPOND_MODE == "mention_only":
            return False
        return bool(self._QUESTION_PATTERNS.search(text))

    async def _transcribe_voice_attachment(
        self,
        voice_att: discord.Attachment,
        *,
        language: str | None = "zh",
    ) -> str | None:
        """Transcribe a Discord voice note with Whisper. Returns text or None."""
        import tempfile

        audio_bytes = await voice_att.read()
        suffix = ".ogg"
        if voice_att.filename:
            ext = os.path.splitext(voice_att.filename)[1]
            if ext:
                suffix = ext

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                kwargs: dict = {"model": "whisper-1", "file": f}
                if language:
                    kwargs["language"] = language
                transcript = await self.openai_client.audio.transcriptions.create(**kwargs)
            text = (transcript.text or "").strip()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if text and len(text) > _VOICE_MEMORY_CHARS:
            text = text[:_VOICE_MEMORY_CHARS].rstrip() + "…"
        return text or None

    async def _resolve_user_text(self, message: discord.Message) -> tuple[str, str | None]:
        """Build the RAG question text.

        Returns ``(user_text, skip_or_error)`` where the second value is:
        - ``None`` to continue the pipeline
        - ``"silent"`` to drop without replying
        - any other string to reply that message to the user and stop
        """
        user_text = (message.content or "").strip()
        voice_att = self._get_voice_attachment(message)
        if voice_att is None:
            return user_text, None

        reject = self._voice_reject_reason(voice_att)
        if reject:
            return user_text, reject

        try:
            async with message.channel.typing():
                transcript = await self._transcribe_voice_attachment(voice_att, language=None)
        except Exception as exc:
            logger.warning("Failed to transcribe member voice %s: %s", message.id, exc)
            if user_text:
                return user_text, None
            return "", "没听清这条语音，请再发一次，或直接打字提问。"

        if not transcript:
            logger.info("Member voice transcription empty (id=%s)", message.id)
            if user_text:
                return user_text, None
            return "", "没听清这条语音，请再发一次，或直接打字提问。"

        logger.info(
            "Member voice transcribed (id=%s, len=%d): %s",
            message.id, len(transcript), transcript[:100],
        )

        if not user_text and not self._voice_transcript_wants_reply(message, transcript):
            logger.info(
                "跳过: 语音转写后不像提问 (id=%s, text=%s)",
                message.id, transcript[:80],
            )
            return "", "silent"

        if user_text:
            return f"{user_text}\n（语音：{transcript}）", None
        return transcript, None

    async def _handle_owner_voice_message(self, message: discord.Message) -> None:
        """Transcribe an owner's Discord voice note via Whisper and auto-learn it."""
        voice_att = self._get_voice_attachment(message)
        if voice_att is None:
            return

        reject = self._voice_reject_reason(voice_att)
        if reject:
            logger.info("Owner voice skipped (%s) id=%s", reject, message.id)
            return

        try:
            text = await self._transcribe_voice_attachment(voice_att, language="zh")
            if not text or len(text) < 5:
                logger.info(
                    "Voice transcription too short, skipping (id=%s, len=%d)",
                    message.id, len(text) if text else 0,
                )
                return

            logger.info(
                "Voice transcription complete (id=%s, len=%d): %s",
                message.id, len(text), text[:100],
            )

            doc_id = f"voice_{message.id}"
            existing = await self.collection.get(ids=[doc_id], include=[])
            if existing["ids"]:
                return

            response = await self.openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[text],
            )
            embedding = response.data[0].embedding

            await self.collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[text],
                metadatas=[{
                    "type": "owner_voice",
                    "source": "discord_live_voice",
                    "channel_id": str(message.channel.id),
                    "message_id": str(message.id),
                    "author_id": str(message.author.id),
                    "timestamp": message.created_at.isoformat(),
                }],
            )
            logger.info("Auto-learned voice message %s (%d chars)", message.id, len(text))
        except Exception as exc:
            logger.warning("Failed to transcribe/store owner voice message %s: %s", message.id, exc)

    # ── Queue worker ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_image_urls(message: discord.Message) -> list[str]:
        """Extract image URLs from message attachments and embeds."""
        urls: list[str] = []
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                urls.append(att.url)
        for embed in message.embeds:
            if embed.image and embed.image.url:
                urls.append(embed.image.url)
            if embed.thumbnail and embed.thumbnail.url:
                urls.append(embed.thumbnail.url)
        return urls[:4]  # GPT-4o supports up to ~4 images per request

    async def _periodic_save_loop(self) -> None:
        """Periodically flush ``_last_seen`` to disk (every 30 s)."""
        try:
            while True:
                await asyncio.sleep(30)
                if self._last_seen_dirty:
                    self._save_last_seen()
                    self._last_seen_dirty = False
        except asyncio.CancelledError:
            pass

    async def _process_queue(self) -> None:
        """Background task that processes queued messages one at a time."""
        try:
            while True:
                message = await self._queue.get()
                try:
                    await self._handle_message(message)
                except Exception as exc:
                    logger.exception("Error processing message %s: %s", message.id, exc)
                finally:
                    self._queue.task_done()
                    self._last_seen_dirty = True
        except asyncio.CancelledError:
            logger.info("Queue worker cancelled — draining remaining items")
            # Best-effort: drain any already-queued items
            while not self._queue.empty():
                try:
                    message = self._queue.get_nowait()
                    await self._handle_message(message)
                    self._queue.task_done()
                except Exception:
                    break

    # ── Offline backfill ────────────────────────────────────────

    def _load_last_seen(self) -> dict[int, int]:
        try:
            with open(OFFLINE_LAST_SEEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {int(k): int(v) for k, v in data.items()}
        except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
            return {}

    def _save_last_seen(self) -> None:
        if not self._last_seen:
            return
        try:
            from bot.utils import atomic_json_write
            atomic_json_write(
                OFFLINE_LAST_SEEN_FILE,
                {str(k): v for k, v in self._last_seen.items()},
            )
        except OSError as exc:
            logger.warning("Failed to save last_seen state: %s", exc)

    async def _backfill_offline_messages(self) -> None:
        """On reconnect, scan target channels for unanswered questions and enqueue them."""
        if self._backfill_lock.locked():
            logger.info("Backfill: already running, skip duplicate trigger")
            return
        async with self._backfill_lock:
            # If TARGET_CHANNEL_IDS is not configured, fall back to channels we've previously
            # observed messages in (recorded in last_seen.json from prior runs).
            if TARGET_CHANNEL_IDS:
                channel_ids = list(TARGET_CHANNEL_IDS)
            else:
                channel_ids = list(self._last_seen.keys())
                if not channel_ids:
                    logger.info(
                        "Backfill: no TARGET_CHANNEL_IDS configured and no prior last_seen state — "
                        "nothing to scan on first deploy. Set TARGET_CHANNEL_IDS in .env to enable "
                        "backfill from the start, or wait until the bot has seen live messages "
                        "(future reconnects will then backfill those channels)."
                    )
                    return
                logger.info(
                    "Backfill: TARGET_CHANNEL_IDS empty — falling back to %d channel(s) from last_seen state",
                    len(channel_ids),
                )
            total_enqueued = 0
            for channel_id in channel_ids:
                try:
                    total_enqueued += await self._backfill_channel(channel_id)
                except Exception as exc:
                    logger.exception("Backfill failed for channel %d: %s", channel_id, exc)
            self._save_last_seen()
            logger.info("Backfill complete: %d unanswered question(s) enqueued", total_enqueued)

    async def _backfill_channel(self, channel_id: int) -> int:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden) as exc:
                logger.warning("Backfill: cannot access channel %d (%s)", channel_id, exc)
                return 0

        last_id = self._last_seen.get(channel_id)
        if last_id:
            after: discord.Object | object = discord.Object(id=last_id)
            window_desc = f"after msg {last_id}"
        else:
            after = discord.utils.utcnow() - timedelta(hours=OFFLINE_BACKFILL_LOOKBACK_HOURS)
            window_desc = f"last {OFFLINE_BACKFILL_LOOKBACK_HOURS}h"

        messages: list[discord.Message] = []
        try:
            async for msg in channel.history(
                limit=OFFLINE_BACKFILL_MAX_PER_CHANNEL,
                after=after,
                oldest_first=True,
            ):
                messages.append(msg)
        except discord.Forbidden:
            logger.warning("Backfill: no read permission for channel %d", channel_id)
            return 0

        if not messages:
            logger.info("Backfill channel %d (%s): no new messages", channel_id, window_desc)
            return 0

        # Build set of message ids already answered.
        # (1) Explicit replies via Discord's reply feature (message reference).
        # (2) Heuristic: any non-trivial owner post within N minutes AFTER a user
        #     question is treated as having addressed the channel — the owner was
        #     clearly online at that moment. Prevents the bot from re-answering
        #     questions the owner already handled without using the reply feature.
        bot_user_id = self.bot.user.id if self.bot.user else 0
        answered: set[int] = set()
        for msg in messages:
            if msg.author.id in (OWNER_USER_ID, bot_user_id) and msg.reference:
                ref_id = msg.reference.message_id
                if ref_id:
                    answered.add(ref_id)

        window_min = OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES
        if window_min > 0:
            window = timedelta(minutes=window_min)
            owner_post_times = [
                m.created_at for m in messages
                if not m.author.bot
                and m.author.id == OWNER_USER_ID
                and m.content
                and len(m.content.strip()) >= 5  # ignore trivial acks / emoji
            ]
            if owner_post_times:
                # messages are oldest_first, so owner_post_times is already sorted
                heuristic_hits = 0
                owner_idx = 0
                for msg in messages:
                    if msg.author.bot or msg.author.id == OWNER_USER_ID:
                        continue
                    if msg.id in answered:
                        continue
                    # Advance pointer to the first owner post at/after this message
                    while (
                        owner_idx < len(owner_post_times)
                        and owner_post_times[owner_idx] < msg.created_at
                    ):
                        owner_idx += 1
                    if owner_idx >= len(owner_post_times):
                        break
                    if owner_post_times[owner_idx] - msg.created_at <= window:
                        answered.add(msg.id)
                        heuristic_hits += 1
                if heuristic_hits:
                    logger.info(
                        "Backfill channel %d: %d question(s) marked answered by owner-post-window heuristic (%.0f min)",
                        channel_id, heuristic_hits, window_min,
                    )

        enqueued = 0
        learned = 0
        already_answered = 0
        for msg in messages:
            # Always advance the cursor so we don't re-scan these messages next reconnect
            if msg.id > self._last_seen.get(channel_id, 0):
                self._last_seen[channel_id] = msg.id

            # Owner messages that arrived during downtime: auto-learn them into ChromaDB.
            # _learn_owner_message is idempotent (checks for existing doc_id), so safe to call.
            if (
                not msg.author.bot
                and msg.author.id == OWNER_USER_ID
                and msg.content
                and msg.content.strip()
            ):
                asyncio.create_task(self._learn_owner_message(msg))
                learned += 1
                continue

            if msg.id in answered:
                already_answered += 1
                continue
            if self._should_skip(msg):
                continue
            await self._queue.put(msg)
            enqueued += 1

        logger.info(
            "Backfill channel %d (%s): scanned %d, enqueued %d unanswered, "
            "skipped %d already-answered-by-owner, learned %d owner post(s)",
            channel_id, window_desc, len(messages),
            enqueued, already_answered, learned,
        )
        return enqueued

    async def _handle_message(self, message: discord.Message) -> None:
        """Full pipeline: retrieve → generate → route → respond."""
        start = time.time()

        # Build conversation history — use thread history for threads, else per-channel memory
        in_thread = self._is_thread(message.channel)
        if in_thread:
            conversation_history = await self._fetch_thread_context(message.channel)
        else:
            conversation_history = self._format_memory(message.channel.id)

        # Resolve text (Whisper-transcribe Discord voice notes when present)
        user_text, voice_status = await self._resolve_user_text(message)
        if voice_status == "silent":
            return
        if voice_status:
            try:
                await message.reply(
                    voice_status,
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except Exception:
                pass
            return
        if not user_text and not self._get_image_urls(message):
            logger.info("跳过: 无文字且无图片 (id=%s)", message.id)
            return

        # Auto language detection — append reply language instruction
        if (
            AUTO_LANG_DETECT
            and user_text
            and is_feature_enabled_for_channel(
                FEATURE_LANG_DETECT,
                FEATURE_LANG_DETECT_CANARY_CHANNEL_IDS,
                message.channel.id,
            )
        ):
            from bot.lang_detect import detect_language, get_reply_lang_instruction
            detected_lang = detect_language(user_text)
            lang_instruction = get_reply_lang_instruction(detected_lang)
            if lang_instruction:
                conversation_history += lang_instruction

        # Record the user's question in memory
        self._add_to_memory(message.channel.id, "user",
                            user_text if user_text else "[图片]")

        # Check if message contains images
        image_urls = self._get_image_urls(message)

        # ── Purchase-intent conversion (skip RAG, send product CTA) ──
        if (
            PROMO_ENABLED
            and INTENT_CONVERT_ENABLED
            and user_text.strip()
            and not image_urls
            and message.author.id != OWNER_USER_ID
        ):
            handled = await self._maybe_handle_purchase_intent(message, user_text)
            if handled:
                return

        if image_urls:
            # ── Vision pipeline (image analysis) ──
            logger.info("检测到图片消息: %d 张图片, 文字=%r",
                        len(image_urls), user_text[:50] if user_text else "")
            # Retrieve RAG context for chart comparison when user provides text
            vision_context: list[dict] = []
            if user_text and user_text.strip():
                try:
                    vision_context = await retrieve_context(
                        question=user_text,
                        collection=self.collection,
                        openai_client=self.openai_client,
                        top_k=3,
                    )
                except Exception as exc:
                    logger.warning("RAG context retrieval for vision failed: %s", exc)
            answer, confidence = await analyze_image(
                image_urls=image_urls,
                user_text=user_text,
                openai_client=self.openai_client,
                conversation_history=conversation_history,
                context_chunks=vision_context if vision_context else None,
            )
            context_chunks: list[dict] = vision_context
            best_distance = 0.0  # images bypass RAG distance check
        else:
            # ── Standard RAG pipeline (text only) ──
            answer, confidence, context_chunks = await run_rag_pipeline(
                question=user_text,
                collection=self.collection,
                openai_client=self.openai_client,
                conversation_history=conversation_history,
            )
            best_distance = 1.0
            if context_chunks:
                best_distance = min(c.get("distance", 1.0) for c in context_chunks)

        routing = route_answer(
            answer=answer,
            confidence=confidence,
            context_count=len(context_chunks),
            best_distance=best_distance,
            question=user_text,
        )

        # Safety guardrails: high-risk content can be forced to owner review.
        if is_feature_enabled_for_channel(
            FEATURE_SAFETY_GUARDRAILS,
            FEATURE_SAFETY_GUARDRAILS_CANARY_CHANNEL_IDS,
            message.channel.id,
        ):
            from bot.guardrails import detect_high_risk_signals
            risk_hits = detect_high_risk_signals(user_text, routing["answer"])
            if risk_hits and routing["action"] == "auto_reply":
                if GUARDRAIL_MODE == "disclaimer":
                    routing["answer"] = f"{routing['answer']}\n\n{GUARDRAIL_DISCLAIMER}"
                    routing["reason"] += " + guardrail disclaimer"
                else:
                    routing["action"] = "forward_to_owner"
                    routing["reason"] = "high-risk signal detected by guardrails"

        # Clarification follow-up: ask one clarifying question for low-confidence
        # auto replies instead of sending an ambiguous answer directly.
        if (
            routing["action"] == "auto_reply"
            and not image_urls
            and is_feature_enabled_for_channel(
                FEATURE_CLARIFICATION_FOLLOWUP,
                FEATURE_CLARIFICATION_CANARY_CHANNEL_IDS,
                message.channel.id,
            )
        ):
            from bot.clarification import build_clarification_reply, needs_clarification
            if needs_clarification(confidence, CLARIFICATION_CONFIDENCE_MAX):
                routing["answer"] = build_clarification_reply(user_text)
                routing["reason"] += " + clarification follow-up"

        elapsed_ms = int((time.time() - start) * 1000)

        # Record stats
        bot_stats.record_query(
            question=user_text[:200],
            channel_id=message.channel.id,
            confidence=confidence,
            action=routing["action"],
            latency_ms=elapsed_ms,
        )

        # Structured log
        logger.info(json.dumps({
            "event": "query_processed",
            "question": (user_text or message.content or "")[:200],
            "author_id": message.author.id,
            "channel_id": message.channel.id,
            "confidence": confidence,
            "action": routing["action"],
            "reason": routing["reason"],
            "context_count": len(context_chunks),
            "best_distance": round(best_distance, 4),
            "response_time_ms": elapsed_ms,
        }))

        if routing["action"] == "auto_reply":
            reply_text = routing["answer"]

            # ── Promotion: append CTA to auto-replies in promo channels ──
            in_promo = is_promo_channel(message.channel.id)
            if in_promo:
                self._auto_reply_counter += 1
                if should_append_cta(self._auto_reply_counter):
                    cta = get_auto_reply_cta()
                    if len(reply_text) + len(cta) <= DISCORD_MAX_LENGTH:
                        reply_text += cta

            # Discord 2000-char limit
            if len(reply_text) > DISCORD_MAX_LENGTH:
                reply_text = reply_text[: DISCORD_MAX_LENGTH - 3] + "..."
            try:
                await message.reply(reply_text, mention_author=False,
                                    allowed_mentions=discord.AllowedMentions.none())
            except (discord.NotFound, discord.HTTPException) as reply_err:
                # Original message was deleted or invalid reference
                logger.warning("Reply to message %s failed (%s), sending to channel instead",
                               message.id, reply_err)
                try:
                    await message.channel.send(reply_text,
                                              allowed_mentions=discord.AllowedMentions.none())
                except Exception:
                    logger.error("Failed to send reply to channel %s", message.channel.id)
            # Record bot's answer in conversation memory
            self._add_to_memory(message.channel.id, "bot", reply_text)
            self._record_reply(message.author.id)
            # Notify the owner that the bot auto-replied (fire-and-forget DM)
            asyncio.create_task(
                notify_owner_auto_reply(
                    bot=self.bot,
                    original_message=message,
                    reply_text=reply_text,
                    confidence=confidence,
                )
            )
        else:
            # Forward to owner for review
            await send_for_review(
                bot=self.bot,
                original_message=message,
                draft_answer=routing["answer"],
                confidence=confidence,
                context_snippets=context_chunks[:3],
                collection=self.collection,
                openai_client=self.openai_client,
            )
            self._record_reply(message.author.id)

            # Also add to the app review queue
            try:
                from bot.review_queue import review_queue
                from bot.api.ws import ws_manager
                item = review_queue.add(
                    channel_id=message.channel.id,
                    channel_name=getattr(message.channel, "name", str(message.channel.id)),
                    message_id=message.id,
                    author_name=str(message.author),
                    author_id=message.author.id,
                    question=user_text,
                    draft_answer=routing["answer"],
                    confidence=confidence,
                    context_snippets=context_chunks[:3] if context_chunks else [],
                    jump_url=getattr(message, "jump_url", ""),
                )
                await ws_manager.broadcast({
                    "type": "review_request",
                    "item": item.to_dict(),
                })
            except Exception as exc:
                logger.debug("Failed to enqueue review item: %s", exc)

            # ── Promotion: send signal CTA when a signal query is forwarded ──
            if is_promo_channel(message.channel.id) and is_signal_query(user_text):
                try:
                    cta_embed = get_signal_cta_embed()
                    await message.channel.send(embed=cta_embed)
                    logger.info("Sent signal CTA embed in channel %s", message.channel.id)
                except Exception as exc:
                    logger.warning("Failed to send signal CTA: %s", exc)

    async def _maybe_handle_purchase_intent(self, message: discord.Message, user_text: str) -> bool:
        """If the message is a subscribe/pricing/trial question, send product CTA and skip RAG."""
        from bot.acquisition import (
            assign_lead_role,
            build_cta_view,
            is_purchase_intent,
            notify_owner_intent,
            record_funnel,
        )

        phrases = is_purchase_intent(user_text)
        if not phrases:
            return False

        embed = get_signal_product_embed()
        view = build_cta_view()
        try:
            await message.reply(
                embed=embed,
                view=view,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            logger.warning("Purchase-intent CTA reply failed: %s", exc)
            return False

        record_funnel("intent_hits")
        record_funnel("cta_posts")
        self._record_reply(message.author.id)
        asyncio.create_task(notify_owner_intent(self.bot, message, phrases))
        if isinstance(message.author, discord.Member):
            asyncio.create_task(assign_lead_role(message.author))
        logger.info("Purchase-intent CTA sent in channel %s (matched=%s)",
                    message.channel.id, phrases)
        return True

    # ── Testimonial collection ───────────────────────────────────────────────

    async def _handle_testimonial(self, message: discord.Message) -> None:
        """Collect a potential testimonial and DM the owner for approval."""
        from bot.testimonials import collect_testimonial
        try:
            await collect_testimonial(self.bot, message)
        except Exception as exc:
            logger.warning("Failed to collect testimonial from message %s: %s",
                           message.id, exc)

    # ── New member welcome ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Send a welcome DM with BigTreeSignal promotion to new members."""
        if member.bot:
            return

        # Enhanced multi-step welcome flow
        if WELCOME_FLOW_ENABLED:
            from bot.welcome_flow import run_welcome_flow
            asyncio.create_task(run_welcome_flow(member))
            return

        if not PROMO_ENABLED:
            return

        # Only welcome if the guild has at least one promo channel
        if not PROMO_CHANNEL_IDS:
            return
        guild_channels = {ch.id for ch in member.guild.channels}
        if not guild_channels.intersection(PROMO_CHANNEL_IDS):
            return

        try:
            embed = get_welcome_embed(member)
            await member.send(embed=embed)
            from bot.acquisition import record_funnel
            record_funnel("welcome_dm_ok")
            logger.info("Sent welcome DM to new member %s (guild=%s)",
                        member, member.guild.name)
        except discord.Forbidden:
            from bot.acquisition import record_funnel
            record_funnel("welcome_dm_blocked")
            logger.info("Cannot DM new member %s — DMs disabled", member)
        except Exception as exc:
            from bot.acquisition import record_funnel
            record_funnel("welcome_dm_blocked")
            logger.warning("Failed to send welcome DM to %s: %s", member, exc)

    # ── VIP role recognition ─────────────────────────────────────────────────

    @staticmethod
    def _is_vip(user: discord.User | discord.Member) -> bool:
        """Check if a user has a VIP role (bypasses rate limiting)."""
        if not VIP_ROLE_IDS:
            return False
        if not isinstance(user, discord.Member):
            return False
        return any(role.id in VIP_ROLE_IDS for role in user.roles)

    # ── Keyword alert DM ─────────────────────────────────────────────────────

    async def _send_keyword_alert(self, message: discord.Message, keywords: list[str]) -> None:
        """DM the owner when a keyword alert is triggered."""
        try:
            owner = await self.bot.fetch_user(OWNER_USER_ID)
            if owner is None:
                return
            kw_str = ", ".join(f"`{k}`" for k in keywords)
            embed = discord.Embed(
                title="🔔 关键词监控触发",
                description=f"**关键词:** {kw_str}\n**作者:** {message.author}\n**频道:** {getattr(message.channel, 'name', str(message.channel.id))}\n\n{message.content[:500]}",
                color=discord.Color.red(),
            )
            if hasattr(message, "jump_url"):
                embed.add_field(name="链接", value=message.jump_url, inline=False)
            await owner.send(embed=embed)
            logger.info("Keyword alert sent to owner: keywords=%s, msg=%s", keywords, message.id)
        except Exception as exc:
            logger.warning("Failed to send keyword alert: %s", exc)

    # ── Feedback reactions (👍/👎) ────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Track 👍/👎 reactions on bot replies for satisfaction feedback."""
        if not FEEDBACK_ENABLED:
            return
        if payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return
        emoji = str(payload.emoji)
        if emoji not in ("👍", "👎"):
            return

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden):
            return

        # Only track reactions on the bot's own messages
        if message.author.id != (self.bot.user.id if self.bot.user else 0):
            return

        # Try to find the original question (the message this was a reply to)
        question = ""
        if message.reference and message.reference.message_id:
            try:
                ref_msg = await channel.fetch_message(message.reference.message_id)
                question = ref_msg.content[:300] if ref_msg.content else ""
            except Exception:
                pass

        from bot.feedback import record_feedback
        record_feedback(
            message_id=payload.message_id,
            channel_id=payload.channel_id,
            user_id=payload.user_id,
            question=question,
            answer=message.content[:300] if message.content else "",
            is_positive=(emoji == "👍"),
        )

        if (
            emoji == "👎"
            and is_feature_enabled_for_channel(
                FEATURE_FEEDBACK_LEARNING,
                FEATURE_FEEDBACK_LEARNING_CANARY_CHANNEL_IDS,
                payload.channel_id,
            )
        ):
            from bot.feedback_learning import record_gap_question
            if question:
                record_gap_question(question, source="thumbs_down_feedback")
