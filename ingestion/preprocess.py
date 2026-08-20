"""Preprocess Discord chat export JSON into chunks ready for embedding."""

import json
import os
import re
import uuid
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tiktoken

logger = logging.getLogger(__name__)

# Cache the tiktoken encoding at module level to avoid recreating it on every call.
_ENC = tiktoken.get_encoding("cl100k_base")


# ── helpers ──────────────────────────────────────────────────────────────────

def _token_count(text: str) -> int:
    return len(_ENC.encode(text))


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp string into a timezone-aware datetime."""
    # Handle various formats from DiscordChatExporter
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ── public API ───────────────────────────────────────────────────────────────

def load_exports(export_dir: str) -> tuple[list[dict], dict[str, dict]]:
    """Load all JSON export files.

    Returns
    -------
    messages : list[dict]
        Flat list of all messages across all exports, sorted by timestamp.
    users : dict[str, dict]
        Mapping of user-id → {name, nickname} gathered from messages.
    """
    export_path = Path(export_dir)
    all_messages: list[dict] = []
    users: dict[str, dict] = {}

    json_files = list(export_path.glob("*.json"))
    if not json_files:
        logger.warning("No JSON files found in %s", export_dir)
        return [], {}

    for fp in json_files:
        logger.info("Loading export file: %s", fp.name)
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages = data.get("messages", [])
        channel_id = str(data.get("channel", {}).get("id", "unknown"))

        for msg in messages:
            msg["_channel_id"] = channel_id
            # collect user info
            author = msg.get("author", {})
            uid = str(author.get("id", ""))
            if uid:
                users[uid] = {
                    "name": author.get("name", ""),
                    "nickname": author.get("nickname") or author.get("name", ""),
                }
            all_messages.append(msg)

    # sort by timestamp
    all_messages.sort(key=lambda m: m.get("timestamp", ""))
    logger.info("Loaded %d messages from %d file(s)", len(all_messages), len(json_files))
    return all_messages, users


def filter_owner_messages(messages: list[dict], owner_id: str) -> list[dict]:
    """Keep only messages authored by the owner."""
    return [
        m for m in messages
        if str(m.get("author", {}).get("id", "")) == owner_id
    ]


def build_qa_pairs(
    messages: list[dict],
    owner_id: str,
) -> list[dict]:
    """Build Q&A pairs from reply chains.

    For every owner message that is a reply to another user's message,
    create a paired document containing both the question and the answer.
    """
    msg_index: dict[str, dict] = {str(m.get("id", "")): m for m in messages}
    pairs: list[dict] = []

    for msg in messages:
        if str(msg.get("author", {}).get("id", "")) != owner_id:
            continue
        ref = msg.get("reference")
        if not ref:
            continue
        ref_id = str(ref.get("messageId", ""))
        original = msg_index.get(ref_id)
        if not original:
            continue
        # skip if the original message is also the owner (self-reply)
        if str(original.get("author", {}).get("id", "")) == owner_id:
            continue

        q_content = original.get("content", "").strip()
        a_content = msg.get("content", "").strip()
        if not q_content or not a_content:
            continue

        pairs.append({
            "text": f"Q: {q_content}\nA: {a_content}",
            "metadata": {
                "source_message_id": str(msg.get("id", "")),
                "timestamp": msg.get("timestamp", ""),
                "type": "qa_pair",
                "question": q_content,
                "channel_id": msg.get("_channel_id", ""),
            },
        })

    logger.info("Built %d Q&A pairs", len(pairs))
    return pairs


def group_consecutive(
    messages: list[dict],
    owner_id: str,
    window_seconds: int = 120,
) -> list[dict]:
    """Merge consecutive owner messages within *window_seconds* into single blocks.

    Messages from other users between two owner messages break the group.
    """
    owner_msgs = [
        m for m in messages
        if str(m.get("author", {}).get("id", "")) == owner_id
        and m.get("content", "").strip()
    ]
    if not owner_msgs:
        return []

    # Build index of all message timestamps for gap detection
    groups: list[list[dict]] = []
    current_group: list[dict] = [owner_msgs[0]]

    for prev, cur in zip(owner_msgs, owner_msgs[1:]):
        prev_ts = _parse_timestamp(prev["timestamp"])
        cur_ts = _parse_timestamp(cur["timestamp"])
        diff = (cur_ts - prev_ts).total_seconds()
        if diff <= window_seconds and prev.get("_channel_id") == cur.get("_channel_id"):
            current_group.append(cur)
        else:
            groups.append(current_group)
            current_group = [cur]
    groups.append(current_group)

    results: list[dict] = []
    for group in groups:
        merged_text = "\n".join(m.get("content", "").strip() for m in group)
        if not merged_text.strip():
            continue
        doc_type = "grouped" if len(group) > 1 else "standalone"
        results.append({
            "text": merged_text,
            "metadata": {
                "source_message_id": str(group[0].get("id", "")),
                "timestamp": group[0].get("timestamp", ""),
                "type": doc_type,
                "channel_id": group[0].get("_channel_id", ""),
            },
        })

    logger.info("Grouped into %d blocks (%d standalone, %d grouped)",
                len(results),
                sum(1 for r in results if r["metadata"]["type"] == "standalone"),
                sum(1 for r in results if r["metadata"]["type"] == "grouped"))
    return results


def clean_message(content: str, users: dict[str, dict]) -> str:
    """Clean Discord formatting and resolve @mentions to readable names."""

    def _replace_mention(match: re.Match) -> str:
        uid = match.group(1)
        user = users.get(uid)
        if user:
            return f"@{user['nickname'] or user['name']}"
        return match.group(0)

    # Resolve <@USER_ID> and <@!USER_ID> mentions
    content = re.sub(r"<@!?(\d+)>", _replace_mention, content)
    # Resolve <#CHANNEL_ID> — just strip to #channel
    content = re.sub(r"<#(\d+)>", "#channel", content)
    # Resolve <@&ROLE_ID> — strip to @role
    content = re.sub(r"<@&(\d+)>", "@role", content)
    # Strip custom emoji to just the name: <:name:id> → :name:
    content = re.sub(r"<a?:(\w+):\d+>", r":\1:", content)

    return content.strip()


def chunk_text(
    text: str,
    max_tokens: int = 500,
    overlap: int = 50,
) -> list[str]:
    """Split text into chunks that each fit within *max_tokens*.

    Splits at paragraph boundaries first, then sentence boundaries.
    """
    if _token_count(text) <= max_tokens:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        candidate = (current_chunk + "\n\n" + para).strip() if current_chunk else para
        if _token_count(candidate) <= max_tokens:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If a single paragraph exceeds max_tokens, split by sentences
            if _token_count(para) > max_tokens:
                sentences = re.split(r"(?<=[.!?。！？])\s*", para)
                # If sentence splitting didn't help (no punctuation), hard-split by words
                if len(sentences) == 1 and _token_count(sentences[0]) > max_tokens:
                    tokens = _ENC.encode(para)
                    for start in range(0, len(tokens), max_tokens):
                        chunk_tokens = tokens[start:start + max_tokens]
                        chunks.append(_ENC.decode(chunk_tokens))
                    current_chunk = ""
                    continue
                current_chunk = ""
                for sent in sentences:
                    candidate = (current_chunk + " " + sent).strip() if current_chunk else sent
                    if _token_count(candidate) <= max_tokens:
                        current_chunk = candidate
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sent
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    # Add overlap between chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tokens = _ENC.encode(chunks[i - 1])
            overlap_text = _ENC.decode(prev_tokens[-overlap:]) if len(prev_tokens) > overlap else ""
            overlapped.append((overlap_text + " " + chunks[i]).strip())
        chunks = overlapped

    return chunks


def _is_trivial(content: str) -> bool:
    """Return True for messages too short / empty to be useful."""
    stripped = content.strip()
    if len(stripped) < 5:
        return True
    # purely a URL
    if re.match(r"^https?://\S+$", stripped):
        return True
    return False


def preprocess_all(
    export_dir: str,
    owner_id: str,
    max_tokens: int = 500,
    overlap: int = 50,
) -> list[dict]:
    """Full pipeline: load → pair → group → clean → chunk.

    Returns list of ``{text, metadata}`` dicts ready for embedding.
    """
    messages, users = load_exports(export_dir)
    if not messages:
        logger.error("No messages loaded — check export directory: %s", export_dir)
        return []

    # 1. Build Q&A pairs (highest value)
    qa_pairs = build_qa_pairs(messages, owner_id)

    # 2. Group consecutive owner messages
    grouped = group_consecutive(messages, owner_id)

    # Combine (Q&A pairs + grouped standalone blocks)
    # Deduplicate: if a message already appeared in a Q&A pair, skip it in grouped
    qa_msg_ids = {d["metadata"]["source_message_id"] for d in qa_pairs}
    standalone_docs = [
        d for d in grouped
        if d["metadata"]["source_message_id"] not in qa_msg_ids
    ]

    all_docs = qa_pairs + standalone_docs
    logger.info("Total raw documents before cleaning: %d", len(all_docs))

    # 3. Clean and chunk
    final: list[dict] = []
    for doc in all_docs:
        cleaned = clean_message(doc["text"], users)
        if _is_trivial(cleaned):
            continue
        chunks = chunk_text(cleaned, max_tokens=max_tokens, overlap=overlap)
        for i, chunk in enumerate(chunks):
            meta = dict(doc["metadata"])
            meta["chunk_index"] = i
            meta["total_chunks"] = len(chunks)
            final.append({
                "id": f"{meta['source_message_id']}_{i}" if len(chunks) > 1 else meta["source_message_id"],
                "text": chunk,
                "metadata": meta,
            })

    logger.info("Preprocessing complete: %d documents ready for embedding", len(final))
    return final
