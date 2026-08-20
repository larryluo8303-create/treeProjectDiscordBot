"""SLA and reliability monitoring helpers."""

import logging
import time
from collections import deque

from bot.config import (
    OWNER_USER_ID,
    SLA_ALERT_COOLDOWN_SECONDS,
    SLA_OPENAI_ERROR_RATE_THRESHOLD,
    SLA_P95_LATENCY_MS_THRESHOLD,
    SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD,
    SLA_SCHEDULER_MISS_SECONDS,
)

logger = logging.getLogger(__name__)

_openai_calls: deque[tuple[float, bool]] = deque(maxlen=1000)
_scheduler_last_tick: float = time.time()
_last_alert_ts: float = 0.0


def record_openai_call(success: bool) -> None:
    _openai_calls.append((time.time(), success))


def mark_scheduler_tick(now_ts: float | None = None) -> None:
    global _scheduler_last_tick
    _scheduler_last_tick = now_ts or time.time()


def openai_error_rate(window_seconds: int = 3600) -> float:
    cutoff = time.time() - window_seconds
    calls = [ok for ts, ok in _openai_calls if ts >= cutoff]
    if not calls:
        return 0.0
    errors = sum(1 for ok in calls if not ok)
    return errors / len(calls)


def p95_latency_ms(latencies: list[int]) -> int:
    if not latencies:
        return 0
    vals = sorted(latencies)
    idx = min(int(0.95 * len(vals)), len(vals) - 1)
    return vals[idx]


def should_send_alert() -> bool:
    global _last_alert_ts
    now = time.time()
    if now - _last_alert_ts < SLA_ALERT_COOLDOWN_SECONDS:
        return False
    _last_alert_ts = now
    return True


async def evaluate_and_alert(bot, bot_stats, webhook_server=None) -> None:
    """Evaluate SLA metrics and send owner DM/webhook alert if threshold exceeded."""
    from bot.review_queue import review_queue

    alerts: list[str] = []

    recent = list(bot_stats.recent)[-200:]
    p95 = p95_latency_ms([r.latency_ms for r in recent])
    if p95 > SLA_P95_LATENCY_MS_THRESHOLD:
        alerts.append(f"p95 latency={p95}ms>{SLA_P95_LATENCY_MS_THRESHOLD}ms")

    err_rate = openai_error_rate()
    if err_rate > SLA_OPENAI_ERROR_RATE_THRESHOLD:
        alerts.append(f"openai error rate={err_rate:.2%}>{SLA_OPENAI_ERROR_RATE_THRESHOLD:.0%}")

    backlog = review_queue.pending_count
    if backlog > SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD:
        alerts.append(f"review queue backlog={backlog}>{SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD}")

    lag = time.time() - _scheduler_last_tick
    if lag > SLA_SCHEDULER_MISS_SECONDS:
        alerts.append(f"scheduler lag={int(lag)}s>{SLA_SCHEDULER_MISS_SECONDS}s")

    if not alerts or not should_send_alert():
        return

    text = "⚠️ SLA告警\n" + "\n".join(f"- {a}" for a in alerts)
    logger.warning(text)

    if OWNER_USER_ID:
        try:
            owner = await bot.fetch_user(OWNER_USER_ID)
            if owner:
                await owner.send(text)
        except Exception as exc:
            logger.warning("Failed to send SLA owner alert: %s", exc)

    if webhook_server is not None:
        try:
            await webhook_server.send_alert(text)
        except Exception:
            pass
