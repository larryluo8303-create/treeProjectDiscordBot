"""Bot entry point — initialize clients and start the Discord bot."""

import asyncio
import functools
import logging
import os
import signal
import sys

import chromadb
import discord
import openai
from discord.ext import commands

from bot.config import (
    ADMIN_ENABLED,
    API_ENABLED,
    CHROMADB_COLLECTION,
    CHROMADB_PATH,
    DISCORD_BOT_TOKEN,
    OPENAI_API_KEY,
    WEBHOOK_ENABLED,
)
from bot.admin import AdminServer
from bot.auto_mod import AutoModCog
from bot.ban_words import load_ban_words, set_openai_client as set_ban_words_openai
from bot.topic_guard import set_openai_client as set_topic_guard_openai
from bot.chromadb_async import AsyncCollection
from bot.commands import BotCommands, PromotionCommands
from bot.daily_summary import DailySummaryCog
from bot.digest import DigestCog
from bot.health import HealthCog
from bot.ingestion_scheduler import IngestionSchedulerCog
from bot.listener import MessageListener
from bot.news_feed import NewsFeedCog
from bot.promo_monitor import PromoMonitorCog
from bot.scheduler import SchedulerCog
from bot.webhook import WebhookServer
from bot.weekly_summary import WeeklySummaryCog
from bot.youtube_monitor import YouTubeMonitorCog
from bot.acquisition_cog import AcquisitionCog

logger = logging.getLogger(__name__)


def _validate_config() -> None:
    """Check that essential config values are set."""
    errors: list[str] = []
    if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "your_bot_token_here":
        errors.append("DISCORD_BOT_TOKEN is not set")
    if not OPENAI_API_KEY or OPENAI_API_KEY == "your_openai_api_key_here":
        errors.append("OPENAI_API_KEY is not set")
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        sys.exit(1)


async def main() -> None:
    _validate_config()

    # ── OpenAI client ────────────────────────────────────────────────────
    openai_client = openai.AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        timeout=60.0,       # total request timeout in seconds
        max_retries=0,       # we handle retries ourselves in rag._openai_chat_with_retry
    )
    logger.info("OpenAI client initialized")

    # ── Ban words (load list + inject OpenAI for semantic matching) ────
    set_ban_words_openai(openai_client)
    load_ban_words()

    # ── Topic guard (inject OpenAI for GPT classification) ──────────
    set_topic_guard_openai(openai_client)

    # ── ChromaDB ─────────────────────────────────────────────────────────
    chroma_client = chromadb.PersistentClient(path=CHROMADB_PATH)
    try:
        collection = chroma_client.get_collection(CHROMADB_COLLECTION)
        logger.info(
            "ChromaDB collection '%s' loaded — %d documents",
            CHROMADB_COLLECTION,
            collection.count(),
        )
    except Exception:
        logger.warning(
            "ChromaDB collection '%s' not found — creating empty collection. "
            "Run `python -m ingestion.ingest` first to populate it.",
            CHROMADB_COLLECTION,
        )
        collection = chroma_client.get_or_create_collection(
            name=CHROMADB_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    # Wrap in async wrapper so ChromaDB calls don't block the event loop.
    collection = AsyncCollection(collection)

    # ── Discord bot ──────────────────────────────────────────────────────
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.invites = True

    bot = commands.Bot(
        command_prefix="!",
        intents=intents,
        help_command=None,
    )

    @bot.event
    async def on_ready():
        logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
        logger.info("Serving %d guild(s)", len(bot.guilds))
        # Sync slash commands with Discord
        try:
            synced = await bot.tree.sync()
            logger.info("Synced %d slash command(s)", len(synced))
        except Exception as exc:
            logger.warning("Failed to sync slash commands: %s", exc)

    # Register cogs
    await bot.add_cog(MessageListener(bot, collection, openai_client))
    await bot.add_cog(PromotionCommands(bot))
    await bot.add_cog(BotCommands(bot, collection, openai_client))
    await bot.add_cog(SchedulerCog(bot, openai_client))
    await bot.add_cog(HealthCog(bot))
    await bot.add_cog(IngestionSchedulerCog(bot))
    await bot.add_cog(DigestCog(bot))
    await bot.add_cog(NewsFeedCog(bot))
    await bot.add_cog(YouTubeMonitorCog(bot, openai_client))
    await bot.add_cog(AcquisitionCog(bot))
    await bot.add_cog(PromoMonitorCog(bot))
    await bot.add_cog(WeeklySummaryCog(bot, openai_client))
    await bot.add_cog(DailySummaryCog(bot, openai_client))
    await bot.add_cog(AutoModCog(bot))

    # ── Webhook server (optional) ────────────────────────────────────────
    webhook_server = None
    if WEBHOOK_ENABLED:
        webhook_server = WebhookServer(collection, openai_client)
        await webhook_server.start()

    # ── Admin panel (optional) ────────────────────────────────────────────
    admin_server = None
    if ADMIN_ENABLED:
        admin_server = AdminServer(collection, openai_client)
        await admin_server.start()

    # ── API server (FastAPI) ───────────────────────────────────────────────
    api_task = None
    if API_ENABLED:
        from bot.api.server import set_dependencies, run_api_server
        set_dependencies(collection, openai_client, bot)
        api_task = asyncio.create_task(run_api_server())
        logger.info("API server task created")

    # ── Graceful shutdown on SIGTERM / SIGINT ───────────────────────────
    shutdown_event = asyncio.Event()

    def _signal_handler(sig: int) -> None:
        logger.info("Received signal %s — initiating graceful shutdown", signal.Signals(sig).name)
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, functools.partial(_signal_handler, sig))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler; fall back to signal.signal
            signal.signal(sig, lambda s, f: _signal_handler(s))

    # Start the bot
    logger.info("Starting Discord bot...")

    async def _run_bot() -> None:
        try:
            await bot.start(DISCORD_BOT_TOKEN)
        except asyncio.CancelledError:
            pass

    bot_task = asyncio.create_task(_run_bot())

    # Wait for shutdown signal OR bot_task to finish (e.g. on error)
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    wait_tasks = [bot_task, shutdown_task]
    if api_task:
        wait_tasks.append(api_task)
    done, pending = await asyncio.wait(
        wait_tasks,
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    # Graceful teardown
    logger.info("Shutting down — unloading cogs and saving state...")
    if webhook_server:
        await webhook_server.stop()
    if admin_server:
        await admin_server.stop()
    for cog_name in list(bot.cogs):
        try:
            await bot.remove_cog(cog_name)
        except Exception as exc:
            logger.warning("Error unloading cog %s: %s", cog_name, exc)

    if not bot.is_closed():
        await bot.close()
    logger.info("Bot shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
