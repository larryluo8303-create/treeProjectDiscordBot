"""Owner viewpoint summary for the /views slash command."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from bot.config import EXCLUDED_CHANNEL_IDS, LLM_MODEL, OWNER_USER_ID, PROMO_SOURCE_CHANNEL_ID
from bot.rag import _openai_chat_with_retry
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

_DM_CHANNELS_FILE = data_path("data/views_dm_channels.json")

# Keep /views posts scannable in-channel (not essay-length).
_VIEWS_MAX_CHARS = 1200
_VIEWS_MAX_TOKENS = 900

_VIEWS_SYSTEM_PROMPT = (
    "你是频道主观点的精简摘要助手。输入是 Discord 发言与对话记录。\n\n"
    "请用简体中文输出尽量短、清楚的要点总结，像「几分钟读完」的速览卡。\n\n"
    "结构（最多 3 个小标题，每个标题下最多 3 条 bullet）：\n"
    "1. **市场观点** — 立场、方向、关键价位/数据\n"
    "2. **对成员回复** — 只写你的结论与建议（私密对话用「有成员问…」概括，不点名）\n"
    "3. **提醒** — 需要记住的风险或结论（没有可省略整节）\n\n"
    "私密对话里对方的话只作极短上下文，总结中用「有成员问…」概括，"
    "不要点名，不要原文粘贴对方私信或私密帖内容。\n"
    "写法：\n"
    "- 每条 bullet 一句话，只保留结论，不写过程、不重复、不铺垫\n"
    "- 合并重复观点；次要细节直接省略\n"
    "- 用 Discord Markdown（**粗体**小标题、- 列表）\n"
    f"- 全文不超过 {_VIEWS_MAX_CHARS} 个字符（硬限制，宁可少写也不要变长）"
)


def clamp_views_hours(hours: int) -> int:
    return max(1, min(168, int(hours)))


def history_limit_for_hours(hours: int) -> int:
    """Smaller history windows keep /views inside Discord's interaction timeout."""
    hours = clamp_views_hours(hours)
    return max(200, min(1500, hours * 8))


def owner_cap_for_hours(hours: int) -> int:
    """Max owner messages to keep per channel."""
    return max(20, min(50, clamp_views_hours(hours)))


def guild_scan_limit_for_hours(hours: int) -> int:
    """Max messages (any author) to walk per channel before stopping."""
    hours = clamp_views_hours(hours)
    return max(400, min(1500, hours * 15))


def is_guild_text_target(channel: discord.abc.Messageable | None, guild: discord.Guild | None) -> bool:
    if guild is None or channel is None:
        return False
    return isinstance(channel, (discord.TextChannel, discord.Thread))


def _skip_channel_id(cid: int | None) -> bool:
    if cid is None:
        return True
    if cid in EXCLUDED_CHANNEL_IDS:
        return True
    if PROMO_SOURCE_CHANNEL_ID and cid == PROMO_SOURCE_CHANNEL_ID:
        return True
    return False


def list_guild_readable_channels(guild: discord.Guild) -> list[discord.abc.GuildChannel]:
    """Text and forum channels the bot should scan for owner messages."""
    channels: list[discord.abc.GuildChannel] = []
    for ch in list(getattr(guild, "channels", []) or []):
        if not isinstance(ch, (discord.TextChannel, discord.ForumChannel)):
            continue
        if _skip_channel_id(ch.id):
            continue
        channels.append(ch)
    return channels


def load_private_channel_ids() -> list[int]:
    try:
        with open(_DM_CHANNELS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        ids = data.get("ids", data) if isinstance(data, dict) else data
        return [int(x) for x in ids]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []


def remember_private_channel(channel_id: int) -> None:
    """Persist a DM/group-DM id so /views can still find it after restart."""
    try:
        cid = int(channel_id)
    except (TypeError, ValueError):
        return
    ids = load_private_channel_ids()
    if cid in ids:
        return
    ids.append(cid)
    try:
        atomic_json_write(_DM_CHANNELS_FILE, {"ids": ids[-200:]}, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("views: failed to persist DM channel %s: %s", cid, exc)


def remember_owner_private_channel(message: discord.Message) -> None:
    """Record a private channel only when the owner is actually in it."""
    ch = message.channel
    if not isinstance(ch, (discord.DMChannel, discord.GroupChannel)):
        return
    owner_id = OWNER_USER_ID
    if message.author.id == owner_id:
        remember_private_channel(ch.id)
        return
    if isinstance(ch, discord.DMChannel) and getattr(ch.recipient, "id", None) == owner_id:
        remember_private_channel(ch.id)
        return
    if isinstance(ch, discord.GroupChannel):
        recips = list(ch.recipients or [])
        if any(getattr(u, "id", None) == owner_id for u in recips):
            remember_private_channel(ch.id)


_OTHER_CONTEXT_CHARS = 80
_MAX_OTHER_PER_CONVERSATION = 8


def count_owner_view_rows(messages: list[dict]) -> int:
    return sum(1 for m in messages if not str(m.get("kind") or "").endswith("对方"))


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _iter_window_history(channel, since: datetime, max_scan: int):
    """Newest-first until ``since`` or ``max_scan`` messages (any author)."""
    if not hasattr(channel, "history"):
        return
    since = _aware(since)
    scanned = 0
    async for msg in channel.history(limit=max_scan, oldest_first=False):
        scanned += 1
        if _aware(msg.created_at) < since:
            return
        yield msg
        if scanned >= max_scan:
            return


def _clip_other_text(text: str) -> str:
    text = text.strip()
    if len(text) > _OTHER_CONTEXT_CHARS:
        return text[:_OTHER_CONTEXT_CHARS].rstrip() + "…"
    return text


def _speaker_line(msg: discord.Message, owner_id: int) -> str:
    text = (msg.content or "").strip()
    if msg.author.id == owner_id:
        return text
    return f"成员问: {_clip_other_text(text)}"


async def _anonymized_reply_context(channel, msg: discord.Message) -> str:
    if not (msg.reference and msg.reference.message_id):
        return ""
    try:
        ref_msg = msg.reference.resolved
        if ref_msg is None:
            ref_msg = await channel.fetch_message(msg.reference.message_id)
        if ref_msg and ref_msg.content and ref_msg.content.strip():
            return f"[回复成员: {_clip_other_text(ref_msg.content)}]\n"
    except Exception:
        return ""
    return ""


async def collect_owner_messages_in_window(
    bot: commands.Bot,
    channel_ids: list[int],
    owner_id: int,
    since: datetime,
    *,
    owner_cap: int = 40,
    scan_cap: int = 1500,
) -> list[dict]:
    """Collect owner posts/replies by walking newest → oldest until ``since``.

    ``scan_cap`` limits how many channel messages (any author) are read.
    ``owner_cap`` limits how many owner messages are kept per channel.
    Reply quotes are anonymized (no member display names).
    """
    messages: list[dict] = []
    owner_cap = max(1, owner_cap)
    scan_cap = max(50, scan_cap)

    for cid in channel_ids:
        channel = bot.get_channel(cid)
        if channel is None:
            try:
                channel = await bot.fetch_channel(cid)
            except Exception:
                logger.warning("views: cannot access channel %d", cid)
                continue
        if not hasattr(channel, "history"):
            continue

        channel_name = getattr(channel, "name", str(cid))
        owner_count = 0
        try:
            async for msg in _iter_window_history(channel, since, scan_cap):
                if msg.author.id != owner_id:
                    continue
                if not msg.content or not msg.content.strip():
                    continue
                if owner_count >= owner_cap:
                    break
                is_reply = bool(msg.reference and msg.reference.message_id)
                reply_context = await _anonymized_reply_context(channel, msg) if is_reply else ""
                messages.append({
                    "channel": channel_name,
                    "time": msg.created_at.strftime("%m/%d %H:%M"),
                    "content": reply_context + msg.content.strip(),
                    "is_reply": is_reply,
                })
                owner_count += 1
        except discord.Forbidden:
            logger.warning("views: no permission to read channel %d", cid)
        except Exception as exc:
            logger.warning("views: error reading channel %d: %s", cid, exc)

    return messages


async def _collect_conversation(
    channel: discord.abc.Messageable,
    owner_id: int,
    since: datetime,
    *,
    label: str,
    kind_owner: str,
    kind_other: str,
    require_owner: bool = True,
    owner_cap: int = 40,
    scan_cap: int = 1500,
) -> list[dict]:
    """Collect a private thread/DM. Owner text is kept; others are short anonymous context."""
    if not hasattr(channel, "history"):
        return []
    collected: list[dict] = []
    owner_count = 0
    other_count = 0
    try:
        async for msg in _iter_window_history(channel, since, scan_cap):
            if msg.author.bot:
                continue
            if not msg.content or not msg.content.strip():
                continue
            is_owner = msg.author.id == owner_id
            if is_owner:
                if owner_count >= owner_cap:
                    break
                owner_count += 1
            else:
                if other_count >= _MAX_OTHER_PER_CONVERSATION:
                    continue
                other_count += 1
            collected.append({
                "channel": label,
                "time": msg.created_at.strftime("%m/%d %H:%M"),
                "content": _speaker_line(msg, owner_id),
                "is_reply": is_owner,
                "kind": kind_owner if is_owner else kind_other,
            })
    except discord.Forbidden:
        logger.info("views: no access to channel %s", getattr(channel, "id", "?"))
        return []
    except Exception as exc:
        logger.warning("views: history failed for %s: %s", getattr(channel, "id", "?"), exc)
        return []

    if require_owner and owner_count == 0:
        return []
    return collected


def _parent_text_channel(channel: discord.abc.Messageable) -> discord.TextChannel | None:
    parent = channel
    if isinstance(channel, discord.Thread):
        parent = channel.parent
    if isinstance(parent, discord.TextChannel):
        return parent
    return None


async def collect_private_thread_messages(
    bot: commands.Bot,
    channel: discord.abc.Messageable,
    owner_id: int,
    since: datetime,
    limit: int,
) -> list[dict]:
    """Threads under the current text channel: owner-only in public threads;

    both sides in private threads where the owner participated.
    """
    parent = _parent_text_channel(channel)
    if parent is None:
        return []

    current_id = getattr(channel, "id", None)
    threads: list[discord.Thread] = []
    seen: set[int] = set()

    def _add(thread: discord.Thread) -> None:
        if thread.id == current_id or thread.id in seen:
            return
        seen.add(thread.id)
        threads.append(thread)

    for thread in parent.threads:
        _add(thread)
    try:
        async for thread in parent.archived_threads(limit=25):
            _add(thread)
    except (discord.Forbidden, discord.HTTPException, TypeError):
        pass
    try:
        async for thread in parent.archived_threads(private=True, limit=25):
            _add(thread)
    except (discord.Forbidden, discord.HTTPException, TypeError):
        pass

    collected: list[dict] = []
    public_ids: list[int] = []
    for thread in threads:
        is_private = getattr(thread, "type", None) == discord.ChannelType.private_thread
        if is_private:
            label = "私密帖"
            collected.extend(await _collect_conversation(
                thread, owner_id, since,
                label=label, kind_owner="私密帖", kind_other="私密帖对方",
                owner_cap=max(20, min(50, limit)),
                scan_cap=max(400, limit),
            ))
        else:
            public_ids.append(thread.id)

    if public_ids:
        collected.extend(await collect_owner_messages_in_window(
            bot, public_ids, owner_id, since,
            owner_cap=max(20, min(50, limit)),
            scan_cap=max(400, limit),
        ))
    return collected


async def _iter_archived_threads(channel, *, private: bool | None = None, limit: int = 15):
    """Yield archived threads. Omit ``private`` for forum channels (unsupported)."""
    kwargs: dict = {"limit": limit}
    if private is not None:
        kwargs["private"] = private
    try:
        async for thread in channel.archived_threads(**kwargs):
            yield thread
    except (discord.Forbidden, discord.HTTPException, TypeError):
        return


async def collect_guild_owner_messages(
    bot: commands.Bot,
    guild: discord.Guild,
    owner_id: int,
    since: datetime,
    *,
    owner_cap: int,
    scan_cap: int,
) -> tuple[list[dict], set[int]]:
    """Owner posts/replies in every readable guild channel, plus both sides of private threads."""
    public_ids: list[int] = []
    private_threads: list[discord.Thread] = []
    seen: set[int] = set()

    def _add_thread(thread: discord.Thread) -> None:
        if thread.id in seen or _skip_channel_id(thread.id):
            return
        parent_id = getattr(thread, "parent_id", None)
        if parent_id and _skip_channel_id(parent_id):
            return
        seen.add(thread.id)
        if getattr(thread, "type", None) == discord.ChannelType.private_thread:
            private_threads.append(thread)
        else:
            public_ids.append(thread.id)

    for ch in list_guild_readable_channels(guild):
        if isinstance(ch, discord.TextChannel):
            if ch.id not in seen:
                public_ids.append(ch.id)
                seen.add(ch.id)
        for thread in list(getattr(ch, "threads", []) or []):
            _add_thread(thread)
        async for thread in _iter_archived_threads(ch, limit=15):
            _add_thread(thread)
        if isinstance(ch, discord.TextChannel):
            async for thread in _iter_archived_threads(ch, private=True, limit=15):
                _add_thread(thread)

    try:
        for thread in await guild.active_threads():
            _add_thread(thread)
    except (discord.Forbidden, discord.HTTPException):
        pass

    messages = await collect_owner_messages_in_window(
        bot, public_ids, owner_id, since, owner_cap=owner_cap, scan_cap=scan_cap,
    )
    for thread in private_threads[:30]:
        messages.extend(await _collect_conversation(
            thread, owner_id, since,
            label="私密帖", kind_owner="私密帖", kind_other="私密帖对方",
            owner_cap=owner_cap, scan_cap=scan_cap,
        ))
    return messages, seen


async def collect_visible_dm_conversations(
    bot: commands.Bot,
    owner_id: int,
    since: datetime,
    *,
    owner_cap: int = 40,
    scan_cap: int = 1500,
) -> list[dict]:
    """Collect DM/group-DM history the bot is allowed to read.

    Discord does not expose 1:1 DMs between the owner and other members to a bot.
    Included here:
    - Group DMs the bot is in (both sides, only if the owner spoke)
    - Direct DMs between the owner and the bot
    Bot-only DMs with other members are skipped (that is not the owner's conversation).
    """
    channels: list[discord.abc.Messageable] = []
    seen: set[int] = set()

    def _add(ch: object) -> None:
        cid = getattr(ch, "id", None)
        if cid is None or cid in seen:
            return
        if isinstance(ch, (discord.DMChannel, discord.GroupChannel)):
            seen.add(cid)
            channels.append(ch)

    for ch in list(getattr(bot, "private_channels", [])):
        _add(ch)

    for cid in load_private_channel_ids()[-50:]:
        ch = bot.get_channel(cid)
        if ch is None:
            try:
                ch = await bot.fetch_channel(cid)
            except Exception:
                continue
        _add(ch)

    collected: list[dict] = []
    for ch in channels:
        if isinstance(ch, discord.GroupChannel):
            recipient_ids = {u.id for u in (ch.recipients or [])}
            if owner_id not in recipient_ids:
                continue
            label = "私信群"
            rows = await _collect_conversation(
                ch, owner_id, since,
                label=label, kind_owner="私信", kind_other="私信对方",
                owner_cap=owner_cap, scan_cap=scan_cap,
            )
            collected.extend(rows)
            remember_private_channel(ch.id)
            continue

        other = getattr(ch, "recipient", None)
        other_id = getattr(other, "id", None)
        # 1:1 DM is always bot ↔ one user. Only the owner's own DM with the bot
        # contains the owner's words. Member↔bot DMs are not owner conversations.
        if other_id != owner_id:
            continue
        label = "私信:Bot"
        rows = await _collect_conversation(
            ch, owner_id, since,
            label=label, kind_owner="私信", kind_other="私信对方",
            require_owner=True,
            owner_cap=owner_cap, scan_cap=scan_cap,
        )
        collected.extend(rows)
        remember_private_channel(ch.id)

    return collected


async def gather_views_messages(
    bot: commands.Bot,
    channel: discord.abc.Messageable,
    hours: int,
    include_dms: bool = True,
) -> tuple[list[dict], str]:
    """Return (messages, source_note) for /views.

    Scans the whole guild for owner posts/replies, plus Bot-visible DMs.
    """
    hours = clamp_views_hours(hours)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    owner_cap = owner_cap_for_hours(hours)
    scan_cap = guild_scan_limit_for_hours(hours)
    owner_id = OWNER_USER_ID
    guild = getattr(channel, "guild", None)

    messages: list[dict] = []
    seen_ids: set[int] = set()
    scanned_guild = False

    if isinstance(guild, discord.Guild):
        try:
            guild_msgs, seen_ids = await collect_guild_owner_messages(
                bot, guild, owner_id, since,
                owner_cap=owner_cap, scan_cap=scan_cap,
            )
            messages.extend(guild_msgs)
            scanned_guild = True
        except Exception as exc:
            logger.warning("views: guild-wide collect failed: %s", exc)

    # Fallback / supplement: current channel if guild scan missed it (e.g. no guild cache).
    current_id = getattr(channel, "id", None)
    if current_id and current_id not in seen_ids:
        if isinstance(channel, discord.Thread) and getattr(channel, "type", None) == discord.ChannelType.private_thread:
            messages.extend(await _collect_conversation(
                channel, owner_id, since,
                label="私密帖", kind_owner="私密帖", kind_other="私密帖对方",
                owner_cap=owner_cap, scan_cap=scan_cap,
            ))
        else:
            try:
                messages.extend(await collect_owner_messages_in_window(
                    bot, [current_id], owner_id, since,
                    owner_cap=owner_cap, scan_cap=scan_cap,
                ))
            except Exception as exc:
                logger.warning("views: current channel collect failed: %s", exc)

    dm_count = 0
    private_count = sum(1 for m in messages if str(m.get("kind", "")).startswith("私密"))
    if include_dms:
        try:
            dm_msgs = await collect_visible_dm_conversations(
                bot, owner_id, since, owner_cap=owner_cap, scan_cap=scan_cap,
            )
            messages.extend(dm_msgs)
            dm_count = len(dm_msgs)
        except Exception as exc:
            logger.warning("views: DM collect failed: %s", exc)

    extra_bits = []
    if scanned_guild:
        extra_bits.append("已扫描本服务器全部文字频道里你的发言和回复。")
    else:
        extra_bits.append("已扫描当前频道里你的发言和回复。")
    if private_count:
        extra_bits.append(f"已纳入 {private_count} 条你参与过的私密帖对话。")
    if dm_count:
        extra_bits.append(f"已纳入 {dm_count} 条 Bot 可见的群私信/你与 Bot 的私信。")
    extra_bits.append(
        "Discord 不允许 Bot 读取你与成员之间的一对一私信；"
        "服务器频道里你对成员的回复（含对方原话）已纳入。"
        "若希望一对一交流被总结，请在服务器开私密帖并让 Bot 可见。"
    )
    return messages, "".join(extra_bits)


async def generate_views_summary(openai_client, messages_text: str) -> str | None:
    if not messages_text.strip():
        return None
    summary = await _openai_chat_with_retry(
        openai_client,
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _VIEWS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "以下是频道主最近的发言与对话。"
                    "请输出尽量简短、清楚的要点总结（不是长文）：\n\n"
                    f"{messages_text}"
                ),
            },
        ],
        max_tokens=_VIEWS_MAX_TOKENS,
        temperature=0.3,
    )
    if not summary:
        return None
    summary = summary.strip()
    if not summary:
        return None
    if len(summary) > _VIEWS_MAX_CHARS:
        summary = summary[: _VIEWS_MAX_CHARS - 1].rstrip() + "…"
    return summary
