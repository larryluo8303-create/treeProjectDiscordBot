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
    OWNER_USER_ID,
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
from bot.earnings import EarningsCalendarCog
from bot.macro import MacroCog
from bot.movers import MoversCog
from bot.portfolio import PortfolioCog
from bot.premarket import PremarketCog
from bot.technicals import TechnicalsCog
from bot.owner_alerts import OwnerAlertCog
from bot.promo_monitor import PromoMonitorCog
from bot.scheduler import SchedulerCog
from bot.webhook import WebhookServer
from bot.weekly_summary import WeeklySummaryCog
from bot.youtube_monitor import YouTubeMonitorCog
from bot.acquisition_cog import AcquisitionCog
from bot.trial_cog import TrialCog
from bot.credit_cog import CreditCog

# 个股订阅 Cog（2026-10-10 新增）：实现放在 ~/workspace/bot-ops/subscription_cog.py，
# 不在 repo 内；导入失败时降级（不注册），不影响 bot 启动。
sys.path.append(os.path.expanduser("~/workspace/bot-ops"))
try:
    from subscription_cog import SubscriptionCog
except ImportError:
    SubscriptionCog = None

logger = logging.getLogger(__name__)


def _watch_task(task: asyncio.Task, name: str) -> asyncio.Task:
    """Attach a done-callback that loudly logs any unhandled task exception.

    Without this, a fire-and-forget task that raises ends up as
    "Task exception was never retrieved" (or worse — silently swallowed),
    which is how a dead API server or bot connection goes unnoticed.
    """
    def _done_cb(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error(
                "Background task %r raised an unhandled exception", name,
                exc_info=exc,
            )
    task.add_done_callback(_done_cb)
    return task


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
    if not OWNER_USER_ID:
        logger.warning(
            "OWNER_USER_ID is not set — owner review DMs and forward-to-owner "
            "will degrade to a user-facing notice. Set OWNER_USER_ID to your "
            "Discord user ID."
        )


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
        # Sync slash commands with Discord.
        # Guild-only sync: immediate effect, and avoids every command showing
        # twice in the client (guild copy + global copy). Do NOT add a global
        # sync() here.
        try:
            for guild in bot.guilds:
                bot.tree.copy_global_to(guild=guild)
                guild_synced = await bot.tree.sync(guild=guild)
                logger.info(
                    "Synced %d slash command(s) to guild %s (%s)",
                    len(guild_synced), guild.id, guild.name,
                )
        except Exception as exc:
            logger.warning("Failed to sync slash commands: %s", exc)

    # Register cogs
    await bot.add_cog(MessageListener(bot, collection, openai_client))
    await bot.add_cog(PromotionCommands(bot))
    await bot.add_cog(BotCommands(bot, collection, openai_client))
    await bot.add_cog(SchedulerCog(bot, openai_client))
    await bot.add_cog(HealthCog(bot))
    await bot.add_cog(OwnerAlertCog(bot))
    await bot.add_cog(IngestionSchedulerCog(bot))
    await bot.add_cog(DigestCog(bot))
    await bot.add_cog(NewsFeedCog(bot, openai_client))
    await bot.add_cog(EarningsCalendarCog(bot))
    await bot.add_cog(MoversCog(bot))
    await bot.add_cog(PortfolioCog(bot, openai_client))
    await bot.add_cog(PremarketCog(bot))
    await bot.add_cog(MacroCog(bot))
    await bot.add_cog(TechnicalsCog(bot, openai_client))
    await bot.add_cog(YouTubeMonitorCog(bot, openai_client))
    await bot.add_cog(AcquisitionCog(bot))
    await bot.add_cog(TrialCog(bot))
    await bot.add_cog(CreditCog(bot))
    await bot.add_cog(PromoMonitorCog(bot))
    await bot.add_cog(WeeklySummaryCog(bot, openai_client))
    await bot.add_cog(DailySummaryCog(bot, openai_client))
    await bot.add_cog(AutoModCog(bot))
    if SubscriptionCog is not None:
        await bot.add_cog(SubscriptionCog(bot))

    # Persistent owner-review buttons (Approve / Edit / Reject in review
    # DMs): one stateless template view registered for the process
    # lifetime, so button clicks still work after a bot restart — the
    # view rebuilds its state from the review queue. See bot/review.py.
    from bot.review import ReviewView
    bot.add_view(ReviewView(None, "", bot, collection=collection, openai_client=openai_client))

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
    # NOTE: the API exposes admin endpoints, so it refuses to start without
    # credentials (see create_app()). If the operator never configured them,
    # skip the API server with a warning instead of killing the whole bot —
    # most operators only run the Discord bot.
    api_task = None
    if API_ENABLED:
        from bot.api.server import (
            api_credentials_configured,
            set_dependencies,
            run_api_server,
        )
        if api_credentials_configured():
            set_dependencies(collection, openai_client, bot)
            api_task = _watch_task(asyncio.create_task(run_api_server()), "api server")
            logger.info("API server task created")
        else:
            logger.warning(
                "API_ENABLED is true but API_USERNAME/API_PASSWORD/API_SECRET_KEY "
                "are not configured — API server will NOT start. The Discord bot "
                "continues normally. To enable the API, set the credentials "
                "(see .env.example)."
            )

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

    bot_task = _watch_task(asyncio.create_task(_run_bot()), "discord bot")

    # Wait for shutdown signal OR bot_task to finish (e.g. on error)
    shutdown_task = _watch_task(asyncio.create_task(shutdown_event.wait()), "shutdown signal")
    wait_tasks = [bot_task, shutdown_task]
    if api_task:
        wait_tasks.append(api_task)
    done, pending = await asyncio.wait(
        wait_tasks,
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Loud failure: if the Discord bot or API server task died with an
    # exception, the graceful teardown below would otherwise exit 0 as if
    # nothing happened. Log it loudly and exit non-zero after cleanup.
    startup_failed = False
    for name, task in (("discord bot", bot_task), ("api server", api_task)):
        if task is None or task not in done or task.cancelled():
            continue
        exc = task.exception()
        if exc is not None:
            logger.critical(
                "Startup task %r failed — shutting down (exit 1).",
                name, exc_info=exc,
            )
            startup_failed = True

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
    if startup_failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
