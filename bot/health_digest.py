"""Owner daily health digest — DM-only, never posted to channels.

Summarizes the trailing 24 h from :mod:`bot.stats` and DMs the owner once
per day at ``HEALTH_DIGEST_HOUR`` (ET).  Enabled by default because it only
talks to the owner — it never pushes anything to guild channels.
"""

import json
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bot.config import (
    HEALTH_DIGEST_ENABLED,
    HEALTH_DIGEST_HOUR,
    SLA_P95_LATENCY_MS_THRESHOLD,
)
from bot.owner_alerts import _dm_owner
from bot.reliability import p95_latency_ms
from bot.stats import bot_stats
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
STATE_FILE = data_path(os.getenv("HEALTH_DIGEST_STATE_FILE", "data/health_digest_state.json"))

# An error count at/above this in 24 h flips the verdict to "needs attention".
_ERROR_WARN_THRESHOLD = 10


def compute_summary() -> dict:
    """Build a JSON-serializable 24 h summary from bot_stats."""
    records = bot_stats._filter_by_range("24h")
    total = len(records)
    auto = sum(1 for r in records if r.action == "auto_reply")
    fwd = total - auto
    latencies = [int(r.latency_ms) for r in records if int(r.latency_ms or 0) > 0]
    avg_ms = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    p95_ms = p95_latency_ms(latencies)
    errors = bot_stats.error_count_24h()
    limited = bot_stats.rate_limited_count_24h()

    if total == 0:
        verdict = "💤 过去 24 小时无查询（bot 空闲，或长时间离线请检查）"
    elif errors >= _ERROR_WARN_THRESHOLD or p95_ms > SLA_P95_LATENCY_MS_THRESHOLD:
        reasons = []
        if errors >= _ERROR_WARN_THRESHOLD:
            reasons.append(f"错误数 {errors} 偏高")
        if p95_ms > SLA_P95_LATENCY_MS_THRESHOLD:
            reasons.append(f"p95 延迟 {p95_ms}ms 超过阈值 {SLA_P95_LATENCY_MS_THRESHOLD}ms")
        verdict = "⚠️ 需要关注：" + "；".join(reasons)
    else:
        verdict = "✅ 运行正常"
    return {
        "date_str": datetime.now(_ET).strftime("%Y-%m-%d"),
        "total_queries": total,
        "auto_replies": auto,
        "forwards": fwd,
        "avg_latency_ms": avg_ms,
        "p95_latency_ms": p95_ms,
        "errors_24h": errors,
        "rate_limited_24h": limited,
        "verdict": verdict,
    }


def _fmt_latency(ms: float) -> str:
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def build_digest_text(summary: dict) -> str:
    """Format the daily digest message (pure function, no I/O)."""
    lines = [
        f"📊 Bot 每日健康简报（{summary['date_str']}）",
        "",
        "过去 24 小时：",
        f"• 查询数：{summary['total_queries']}"
        f"（自动回复 {summary['auto_replies']}，转人工 {summary['forwards']}）",
        f"• 平均延迟：{_fmt_latency(summary['avg_latency_ms'])}"
        f"，p95：{_fmt_latency(summary['p95_latency_ms'])}",
        f"• 错误数：{summary['errors_24h']}，限流触发：{summary['rate_limited_24h']}",
        "",
        f"一句话结论：{summary['verdict']}",
    ]
    return "\n".join(lines)


def _load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    try:
        atomic_json_write(STATE_FILE, state)
    except OSError as exc:
        logger.warning("Failed to save health digest state: %s", exc)


async def maybe_send_daily_digest(bot, now: datetime | None = None) -> bool:
    """Send the daily digest DM if due. Returns True if a DM was sent.

    Due = enabled, ET hour reached, and not already sent today (ET).
    Owner-DM only; never touches guild channels.
    """
    if not HEALTH_DIGEST_ENABLED:
        return False
    now = now or datetime.now(timezone.utc)
    now_et = now.astimezone(_ET)
    if now_et.hour < HEALTH_DIGEST_HOUR:
        return False
    today = now_et.strftime("%Y-%m-%d")
    if _load_state().get("last_sent_date") == today:
        return False
    text = build_digest_text(compute_summary())
    sent = await _dm_owner(bot, "📊 Bot 每日健康简报", text)
    if sent:
        _save_state({"last_sent_date": today})
        logger.info("Sent daily health digest DM to owner")
    return sent
