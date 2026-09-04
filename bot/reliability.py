"""SLA and reliability monitoring helpers."""

import logging
import time
from collections import deque

from bot.config import (
    OWNER_USER_ID,
    REVIEW_QUEUE_EXPIRE_SECONDS,
    SLA_ALERT_COOLDOWN_SECONDS,
    SLA_OPENAI_ERROR_RATE_THRESHOLD,
    SLA_OPENAI_MIN_CALLS,
    SLA_P95_LATENCY_MS_THRESHOLD,
    SLA_P95_MAX_SAMPLE_MS,
    SLA_P95_MIN_SAMPLES,
    SLA_P95_WINDOW_SECONDS,
    SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD,
    SLA_SCHEDULER_MISS_SECONDS,
)

logger = logging.getLogger(__name__)

_openai_calls: deque[tuple[float, bool]] = deque(maxlen=1000)
_scheduler_last_tick: float = time.time()
_last_alert_ts: float = 0.0
_last_alert_fingerprint: str = ""


def record_openai_call(success: bool) -> None:
    _openai_calls.append((time.time(), success))


def reset_openai_calls() -> None:
    """Clear in-memory OpenAI call samples. Intended for tests."""
    _openai_calls.clear()


def openai_call_count(window_seconds: int = 3600) -> int:
    cutoff = time.time() - window_seconds
    return sum(1 for ts, _ok in _openai_calls if ts >= cutoff)


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


def sla_latencies(
    records,
    *,
    now: float | None = None,
    window_seconds: int = SLA_P95_WINDOW_SECONDS,
    max_sample_ms: int = SLA_P95_MAX_SAMPLE_MS,
) -> list[int]:
    """Latencies eligible for SLA p95: recent, positive, and not hang/restart outliers."""
    now = now if now is not None else time.time()
    cutoff = now - window_seconds
    out: list[int] = []
    for r in records:
        ts = getattr(r, "timestamp", 0) or 0
        if ts < cutoff:
            continue
        ms = int(getattr(r, "latency_ms", 0) or 0)
        if ms <= 0 or ms > max_sample_ms:
            continue
        out.append(ms)
    return out


def should_send_alert() -> bool:
    global _last_alert_ts
    now = time.time()
    if now - _last_alert_ts < SLA_ALERT_COOLDOWN_SECONDS:
        return False
    _last_alert_ts = now
    return True


def _fingerprint(alerts: list[str]) -> str:
    return "\n".join(alerts)


def reset_alert_state() -> None:
    """Reset cooldown/fingerprint. Intended for tests."""
    global _last_alert_ts, _last_alert_fingerprint
    _last_alert_ts = 0.0
    _last_alert_fingerprint = ""


async def evaluate_and_alert(bot, bot_stats, webhook_server=None) -> None:
    """Evaluate SLA metrics and send owner DM/webhook alert if threshold exceeded.

    The same alert set is sent once until it changes or clears. Historical
    stats, zero-latency client calls, and hang/restart outliers are ignored
    for p95 so a single stale sample cannot spam DMs for hours.
    """
    global _last_alert_fingerprint
    from bot.review_queue import review_queue

    alerts: list[str] = []

    review_queue.expire_stale(REVIEW_QUEUE_EXPIRE_SECONDS)

    samples = sla_latencies(bot_stats.recent)
    if len(samples) >= SLA_P95_MIN_SAMPLES:
        p95 = p95_latency_ms(samples)
        if p95 > SLA_P95_LATENCY_MS_THRESHOLD:
            alerts.append(
                f"p95 latency={p95}ms (n={len(samples)}, {SLA_P95_WINDOW_SECONDS // 60}m)"
                f">{SLA_P95_LATENCY_MS_THRESHOLD}ms"
            )

    n_calls = openai_call_count()
    err_rate = openai_error_rate()
    if n_calls >= SLA_OPENAI_MIN_CALLS and err_rate > SLA_OPENAI_ERROR_RATE_THRESHOLD:
        alerts.append(
            f"openai error rate={err_rate:.2%} ({n_calls} calls)"
            f">{SLA_OPENAI_ERROR_RATE_THRESHOLD:.0%}"
        )

    backlog = review_queue.pending_count
    if backlog > SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD:
        alerts.append(f"review queue backlog={backlog}>{SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD}")

    lag = time.time() - _scheduler_last_tick
    if lag > SLA_SCHEDULER_MISS_SECONDS:
        alerts.append(f"scheduler lag={int(lag)}s>{SLA_SCHEDULER_MISS_SECONDS}s")

    if not alerts:
        _last_alert_fingerprint = ""
        return

    fp = _fingerprint(alerts)
    if fp == _last_alert_fingerprint:
        return
    if not should_send_alert():
        return
    _last_alert_fingerprint = fp

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
