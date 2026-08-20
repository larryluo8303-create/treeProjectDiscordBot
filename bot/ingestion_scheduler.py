"""Scheduled ingestion — periodic re-analysis of style and incremental ingest.

Runs the ingestion pipeline and style analysis at configurable intervals
so the knowledge base stays up-to-date without manual intervention.
"""

import asyncio
import logging
import subprocess
import sys
from datetime import datetime, timezone

from discord.ext import commands, tasks

from bot.config import OWNER_USER_ID

logger = logging.getLogger(__name__)

# Defaults (configurable via env in config.py)
import os

INGEST_INTERVAL_HOURS: float = float(os.getenv("INGEST_INTERVAL_HOURS", "0"))
STYLE_INTERVAL_HOURS: float = float(os.getenv("STYLE_INTERVAL_HOURS", "0"))


class IngestionSchedulerCog(commands.Cog):
    """Periodically runs ingestion and style analysis as subprocesses."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._ingest_task: asyncio.Task | None = None
        self._style_task: asyncio.Task | None = None
        self._last_ingest: datetime | None = None
        self._last_style: datetime | None = None

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if INGEST_INTERVAL_HOURS > 0:
            if self._ingest_task is None or self._ingest_task.done():
                self._ingest_task = asyncio.create_task(self._ingest_loop())
                logger.info("Ingestion scheduler started (every %.1fh)", INGEST_INTERVAL_HOURS)

        if STYLE_INTERVAL_HOURS > 0:
            if self._style_task is None or self._style_task.done():
                self._style_task = asyncio.create_task(self._style_loop())
                logger.info("Style re-analysis scheduler started (every %.1fh)", STYLE_INTERVAL_HOURS)

    async def cog_unload(self) -> None:
        for task in (self._ingest_task, self._style_task):
            if task is not None:
                task.cancel()
        self._ingest_task = None
        self._style_task = None

    # ── Loops ─────────────────────────────────────────────────────────────────

    async def _ingest_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(INGEST_INTERVAL_HOURS * 3600)
                await self._run_ingest()
        except asyncio.CancelledError:
            pass

    async def _style_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(STYLE_INTERVAL_HOURS * 3600)
                await self._run_style()
        except asyncio.CancelledError:
            pass

    # ── Subprocess runners ────────────────────────────────────────────────────

    async def _run_subprocess(self, module: str) -> tuple[bool, str]:
        """Run a Python module as a subprocess and return (success, output)."""
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    [sys.executable, "-m", module],
                    capture_output=True,
                    text=True,
                    timeout=3600,  # 1 hour max
                ),
            )
            output = (result.stdout + "\n" + result.stderr).strip()
            if result.returncode == 0:
                return True, output
            return False, output
        except subprocess.TimeoutExpired:
            return False, f"{module} timed out after 1 hour"
        except Exception as exc:
            return False, str(exc)

    async def _run_ingest(self) -> None:
        logger.info("Scheduled ingestion starting...")
        success, output = await self._run_subprocess("ingestion.ingest")
        self._last_ingest = datetime.now(timezone.utc)
        if success:
            logger.info("Scheduled ingestion completed successfully")
            logger.debug("Ingest output: %s", output[-500:] if output else "(empty)")
        else:
            logger.error("Scheduled ingestion failed: %s", output[-500:] if output else "(empty)")
            await self._notify_owner(f"❌ Scheduled ingestion failed:\n```\n{output[-500:]}\n```")

    async def _run_style(self) -> None:
        logger.info("Scheduled style re-analysis starting...")
        success, output = await self._run_subprocess("ingestion.analyze_style")
        self._last_style = datetime.now(timezone.utc)
        if success:
            logger.info("Scheduled style re-analysis completed successfully")
        else:
            logger.error("Scheduled style analysis failed: %s", output[-500:] if output else "(empty)")
            await self._notify_owner(f"❌ Scheduled style analysis failed:\n```\n{output[-500:]}\n```")

    async def _notify_owner(self, text: str) -> None:
        """DM the owner about a failure."""
        try:
            owner = await self.bot.fetch_user(OWNER_USER_ID)
            if owner:
                await owner.send(text[:2000])
        except Exception as exc:
            logger.warning("Failed to DM owner about ingestion failure: %s", exc)

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "ingest_interval_hours": INGEST_INTERVAL_HOURS,
            "style_interval_hours": STYLE_INTERVAL_HOURS,
            "last_ingest": self._last_ingest.isoformat() if self._last_ingest else None,
            "last_style": self._last_style.isoformat() if self._last_style else None,
        }
