"""Owner-only anomaly DM alerts.

Centralizes the "repeated failures -> DM the owner" pattern (previously
duplicated in ``news_feed._alert_owner``).  Event recorders are intentionally
bot-agnostic — ``rag.py`` / ``listener.py`` / ``scheduler.py`` record raw
events, and :func:`evaluate_and_alert` (run as a scheduler subtask every
60 s) checks thresholds and sends DMs.

Rules:
- Every alert goes to the owner's DM **only** — never to a guild channel.
- ``OWNER_USER_ID`` unset/0 -> silently skip (same guard as
  ``review.notify_owner_auto_reply``).
- Per-alert-key cooldown bounds DM frequency.
"""

import logging
import time
from collections import deque

import discord
from discord.ext import commands

from bot.config import (
    ALERT_403_THRESHOLD,
    ALERT_403_WINDOW_SECONDS,
    ALERT_COOLDOWN_SECONDS,
    ALERT_OPENAI_429_THRESHOLD,
    ALERT_OPENAI_429_WINDOW_SECONDS,
    ALERT_RECONNECT_THRESHOLD,
    ALERT_RECONNECT_WINDOW_SECONDS,
    OWNER_USER_ID,
)

logger = logging.getLogger(__name__)

_MAX_EVENTS = 500


def _new_window() -> deque:
    return deque(maxlen=_MAX_EVENTS)


# Raw event timestamps.  Bot-agnostic so producers (rag/listener/scheduler)
# don't need a bot reference.
_openai_429_events: deque = _new_window()
_openai_quota_events: deque = _new_window()
_gateway_reconnects: deque = _new_window()
_discord_403s: deque = _new_window()
# (subtask_name, timestamp, error_text)
_scheduler_failures: deque = _new_window()

# alert_key -> last DM timestamp (cooldown)
_last_alert: dict[str, float] = {}


def reset_alert_state() -> None:
    """Clear all recorded events and cooldowns. Intended for tests."""
    for dq in (_openai_429_events, _openai_quota_events, _gateway_reconnects,
               _discord_403s, _scheduler_failures):
        dq.clear()
    _last_alert.clear()


# ── Event recorders (safe to call from anywhere; never raise) ───────────────

def record_openai_429() -> None:
    """Record one exhausted 429 incident (retries already gave up)."""
    _openai_429_events.append(time.time())


def record_openai_quota_error() -> None:
    """Record one OpenAI auth/quota failure (persistent by nature)."""
    _openai_quota_events.append(time.time())


def record_gateway_reconnect() -> None:
    """Record one gateway disconnect (reconnect storm detection)."""
    _gateway_reconnects.append(time.time())


def record_discord_403() -> None:
    """Record one Discord 403 Forbidden on a send/fetch."""
    _discord_403s.append(time.time())


def note_discord_error(exc: BaseException) -> None:
    """Record a Discord API error if it is a 403; ignore everything else."""
    try:
        if isinstance(exc, discord.Forbidden):
            record_discord_403()
    except Exception:
        pass


def record_scheduler_subtask_failure(name: str, exc: BaseException) -> None:
    """Record one uncaught exception from a scheduler subtask."""
    try:
        _scheduler_failures.append((name, time.time(), f"{type(exc).__name__}: {exc}"[:300]))
    except Exception:
        pass


def _count_since(events: deque, window_seconds: float, now: float) -> int:
    cutoff = now - window_seconds
    return sum(1 for ts in events if ts >= cutoff)


# ── Owner DM ─────────────────────────────────────────────────────────────────

async def _dm_owner(bot, title: str, body: str) -> bool:
    """DM the owner. Returns True if the DM was sent.

    Never raises; silently skips when OWNER_USER_ID is not configured —
    same guard as review.notify_owner_auto_reply.
    """
    if not OWNER_USER_ID:
        return False
    try:
        owner = await bot.fetch_user(OWNER_USER_ID)
    except Exception as exc:
        logger.warning("owner_alerts: could not fetch owner (ID=%s): %s", OWNER_USER_ID, exc)
        return False
    if not owner:
        logger.warning("owner_alerts: fetch_user(%s) returned falsy — skipping", OWNER_USER_ID)
        return False
    embed = discord.Embed(
        title=title,
        description=body[:4000],
        color=discord.Color.red(),
    )
    try:
        await owner.send(embed=embed)
        return True
    except Exception as exc:
        logger.warning("owner_alerts: failed to DM owner: %s", exc)
        return False


def _cooldown_ok(key: str, now: float) -> bool:
    last = _last_alert.get(key, 0.0)
    if now - last < ALERT_COOLDOWN_SECONDS:
        return False
    _last_alert[key] = now
    return True


# ── Evaluation (scheduler subtask) ───────────────────────────────────────────

async def evaluate_and_alert(bot) -> None:
    """Check anomaly windows and DM the owner when thresholds are hit.

    Runs every 60 s as a scheduler subtask.  Never raises — a failure here
    must not kill the scheduler loop (it would be recorded as a subtask
    failure and alerted on the next tick, bounded by cooldown).
    """
    now = time.time()

    # OpenAI 429 incidents (retries exhausted)
    n_429 = _count_since(_openai_429_events, ALERT_OPENAI_429_WINDOW_SECONDS, now)
    if n_429 >= ALERT_OPENAI_429_THRESHOLD and _cooldown_ok("openai_429", now):
        await _dm_owner(
            bot,
            "⚠️ OpenAI 429 限流告警",
            f"过去 {ALERT_OPENAI_429_WINDOW_SECONDS // 60} 分钟内发生 {n_429} 次 429（重试耗尽）。"
            "可能原因：调用量突增 / 额度将用完。建议检查 OpenAI 后台用量与账单。",
        )

    # OpenAI auth / quota errors — persistent, alert on first sight per cooldown
    n_quota = _count_since(_openai_quota_events, ALERT_COOLDOWN_SECONDS, now)
    if n_quota >= 1 and _cooldown_ok("openai_quota", now):
        await _dm_owner(
            bot,
            "🚨 OpenAI 鉴权/额度告警",
            f"检测到 {n_quota} 次 OpenAI 鉴权或额度耗尽错误（API key 无效或余额不足）。"
            "重试无意义，请检查 OPENAI_API_KEY 与账户余额；bot 已自动降级，用户问题可能无回复。",
        )

    # Gateway reconnect storm
    n_re = _count_since(_gateway_reconnects, ALERT_RECONNECT_WINDOW_SECONDS, now)
    if n_re >= ALERT_RECONNECT_THRESHOLD and _cooldown_ok("gateway_reconnect", now):
        await _dm_owner(
            bot,
            "⚠️ Gateway 重连频繁",
            f"过去 {ALERT_RECONNECT_WINDOW_SECONDS // 60} 分钟内网关断线重连 {n_re} 次"
            f"（阈值 {ALERT_RECONNECT_THRESHOLD}）。"
            "可能原因：出口代理抖动 / Discord 机房问题。如持续，请检查代理与网络。",
        )

    # Discord 403 spike — permissions may have been changed
    n_403 = _count_since(_discord_403s, ALERT_403_WINDOW_SECONDS, now)
    if n_403 >= ALERT_403_THRESHOLD and _cooldown_ok("discord_403", now):
        await _dm_owner(
            bot,
            "⚠️ Discord 403 权限告警",
            f"过去 {ALERT_403_WINDOW_SECONDS // 60} 分钟内出现 {n_403} 次 403 Forbidden"
            f"（阈值 {ALERT_403_THRESHOLD}）。"
            "可能是 bot 在某些频道的权限被修改/收回，请检查服务器角色与频道权限设置。",
        )

    # Scheduler subtask failures (one alert per subtask name per cooldown)
    cutoff = now - ALERT_COOLDOWN_SECONDS
    seen: set[str] = set()
    for name, ts, err_text in list(_scheduler_failures):
        if ts < cutoff or name in seen:
            continue
        seen.add(name)
        key = f"scheduler:{name}"
        if _cooldown_ok(key, now):
            await _dm_owner(
                bot,
                "⚠️ 定时任务异常",
                f"调度器子任务 `{name}` 在过去 1 小时内抛出了未捕获异常（已被隔离，不影响其他任务）。\n"
                f"最后一次错误：`{err_text}`\n请查看日志排查。",
            )


class OwnerAlertCog(commands.Cog):
    """Tracks gateway disconnects for reconnect-storm detection."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_disconnect(self) -> None:
        record_gateway_reconnect()
