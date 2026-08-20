"""Lightweight health-check utilities.

Provides:
1. A periodic heartbeat log (every 5 min) — always active.
2. An optional HTTP ``/health`` endpoint via aiohttp — enabled when
   ``HEALTH_PORT`` is set in the environment.
"""

import asyncio
import logging
import os
import time

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

HEALTH_PORT: int = int(os.getenv("HEALTH_PORT", "0"))  # 0 = disabled

# Track bot start time for uptime reporting.
_start_time: float = time.monotonic()


def uptime_seconds() -> float:
    return time.monotonic() - _start_time


class HealthCog(commands.Cog):
    """Cog that emits periodic heartbeat logs and optionally serves /health."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._heartbeat_task: asyncio.Task | None = None
        self._http_runner = None  # aiohttp AppRunner, if enabled

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        if HEALTH_PORT and self._http_runner is None:
            asyncio.create_task(self._start_http())

    async def cog_unload(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._http_runner is not None:
            await self._http_runner.cleanup()
            self._http_runner = None

    # ── Heartbeat ─────────────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(300)  # 5 minutes
                guilds = len(self.bot.guilds) if self.bot.guilds else 0
                latency_ms = round(self.bot.latency * 1000, 1)
                uptime_min = round(uptime_seconds() / 60, 1)
                logger.info(
                    "Heartbeat: uptime=%.1f min, guilds=%d, ws_latency=%.1f ms",
                    uptime_min, guilds, latency_ms,
                )
        except asyncio.CancelledError:
            pass

    # ── Optional HTTP health endpoint ─────────────────────────────────────

    async def _start_http(self) -> None:
        try:
            from aiohttp import web
        except ImportError:
            logger.warning("aiohttp not installed — HTTP health endpoint disabled")
            return

        app = web.Application()
        app.router.add_get("/health", self._handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
        await site.start()
        self._http_runner = runner
        logger.info("Health HTTP endpoint listening on port %d", HEALTH_PORT)

    async def _handle_health(self, request) -> "web.Response":
        from aiohttp import web

        is_ready = self.bot.is_ready()
        status = 200 if is_ready else 503
        return web.json_response(
            {
                "status": "ok" if is_ready else "not_ready",
                "uptime_seconds": round(uptime_seconds(), 1),
                "guilds": len(self.bot.guilds) if self.bot.guilds else 0,
                "ws_latency_ms": round(self.bot.latency * 1000, 1),
            },
            status=status,
        )
