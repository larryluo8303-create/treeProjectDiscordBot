"""Fetch the owner's Discord guild message history into DiscordChatExporter-style JSON.

Read-only: iterates text channels of the guild, fetches up to 3000 messages
per channel, and writes one JSON file per channel to data/exports/ in the
format consumed by ingestion/preprocess.py:

    {"channel": {"id": str},
     "messages": [{"id": str, "timestamp": ISO8601, "author": {"id", "name", "nickname"},
                   "content": str, "reference": {"messageId": str} or null}]}

Run from the repo root with the env file loaded:
    set -a; source ~/workspace/user/files/env.txt; set +a
    .review-venv/bin/python scripts/fetch_owner_history.py
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import discord

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("fetch_history")

GUILD_ID = int(os.environ.get("GUILD_ID", "895349295975370802"))
MESSAGES_PER_CHANNEL = int(os.environ.get("FETCH_LIMIT", "3000"))
EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


def _dce_message(msg: discord.Message) -> dict | None:
    content = (msg.content or "").strip()
    if not content:
        return None
    author = msg.author
    ref = None
    if msg.reference and msg.reference.message_id:
        ref = {"messageId": str(msg.reference.message_id)}
    return {
        "id": str(msg.id),
        "timestamp": msg.created_at.isoformat(),
        "author": {
            "id": str(author.id),
            "name": getattr(author, "name", str(author)),
            "nickname": getattr(author, "display_name", "") or getattr(author, "name", ""),
        },
        "content": content,
        "reference": ref,
    }


class HistoryClient(discord.Client):
    async def on_ready(self):
        try:
            await self._fetch_all()
        finally:
            await self.close()

    async def _fetch_all(self):
        guild = self.get_guild(GUILD_ID)
        if guild is None:
            logger.error("Guild %s not found in guild list", GUILD_ID)
            return
        logger.info("Connected as %s; fetching guild '%s'", self.user, guild.name)
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        total_msgs = 0
        owner_msgs = 0
        owner_id = os.environ.get("OWNER_USER_ID", "")
        channels = [c for c in guild.text_channels]
        logger.info("Found %d text channels", len(channels))

        for idx, channel in enumerate(channels, 1):
            try:
                perms = channel.permissions_for(guild.me)
                if not (perms.read_messages and perms.read_message_history):
                    logger.info("[%d/%d] skip #%s (no read permission)",
                                idx, len(channels), channel.name)
                    continue
                msgs: list[dict] = []
                async for msg in channel.history(limit=MESSAGES_PER_CHANNEL,
                                                 oldest_first=False):
                    d = _dce_message(msg)
                    if d is None:
                        continue
                    msgs.append(d)
                    if d["author"]["id"] == owner_id:
                        owner_msgs += 1
                # DCE order is chronological; sort ascending by id
                msgs.sort(key=lambda m: int(m["id"]))
                out = {"channel": {"id": str(channel.id), "name": channel.name},
                       "messages": msgs}
                fp = EXPORT_DIR / f"channel_{channel.id}.json"
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False)
                total_msgs += len(msgs)
                logger.info("[%d/%d] #%s: %d messages -> %s",
                            idx, len(channels), channel.name, len(msgs), fp.name)
            except (discord.Forbidden, discord.HTTPException) as exc:
                logger.warning("[%d/%d] #%s failed: %s", idx, len(channels),
                               channel.name, exc)

        logger.info("DONE: %d messages total, %d from owner (%s) across %d channels",
                    total_msgs, owner_msgs, owner_id, len(channels))


def _load_env_file(path: str) -> None:
    """Load KEY=VALUE lines (tolerates CRLF) without overriding existing env."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip().strip("\r")
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


_load_env_file(os.path.expanduser("~/workspace/user/files/env.txt"))


def main() -> int:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN is not set")
        return 1
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    # Route through the egress proxy (discord.py does not honor proxy env vars)
    proxy = proxy_auth = None
    env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if env_proxy:
        from urllib.parse import urlsplit

        parts = urlsplit(env_proxy)
        proxy = f"{parts.scheme}://{parts.hostname}:{parts.port}"
        if parts.username:
            from urllib.parse import unquote

            import aiohttp

            proxy_auth = aiohttp.BasicAuth(
                unquote(parts.username), unquote(parts.password or ""))
    client = HistoryClient(intents=intents, proxy=proxy, proxy_auth=proxy_auth)
    client.run(token, log_handler=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
