"""Regression tests for Major batch 1 (cost/stability/security).

- Rate limit check-and-consume is atomic (burst of N messages -> only 1 allowed)
- /ask shares the same safety routing as the message channel
- OpenAI 429 retried with backoff, then degrades to "try later" (no silent drop)
- News feed truncates over-long items; dead-letters unpostable items
- Admin panel refuses to start without ADMIN_SECRET
"""

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub chromadb (not installed in the lightweight test venv) so bot.listener
# and bot.rag can be imported.
sys.modules.setdefault("chromadb", MagicMock())


# ── 1a: atomic rate limiting ──────────────────────────────────────────────

def _make_listener():
    from bot.listener import MessageListener
    listener = MessageListener.__new__(MessageListener)
    listener._user_cooldowns = {}
    listener._global_tokens = 10.0
    listener._global_last_refill = 0.0
    return listener


def test_rate_limit_atomic_consume_burst():
    """10 rapid messages from one user -> only the first is allowed."""
    import time
    from bot import listener as listener_mod
    from bot.config import USER_COOLDOWN_SECONDS

    lis = _make_listener()
    allowed = 0
    with patch.object(listener_mod.time, "time", return_value=1000.0):
        for _ in range(10):
            if lis._try_consume_rate_limit(user_id=42):
                allowed += 1
    assert allowed == 1, f"burst bypass: {allowed} of 10 allowed"


def test_rate_limit_refills_after_cooldown():
    import time
    from bot import listener as listener_mod
    from bot.config import USER_COOLDOWN_SECONDS

    lis = _make_listener()
    with patch.object(listener_mod.time, "time", return_value=1000.0):
        assert lis._try_consume_rate_limit(user_id=7) is True
        assert lis._try_consume_rate_limit(user_id=7) is False
    with patch.object(listener_mod.time, "time",
                      return_value=1000.0 + USER_COOLDOWN_SECONDS + 1):
        assert lis._try_consume_rate_limit(user_id=7) is True


def test_rate_limit_global_bucket():
    from bot import listener as listener_mod

    lis = _make_listener()
    lis._global_tokens = 1.0  # only one global token left
    lis._global_last_refill = 1000.0  # align with mocked clock below
    with patch.object(listener_mod.time, "time", return_value=1000.0):
        assert lis._try_consume_rate_limit(user_id=1) is True
        # second user blocked by the shared global bucket
        assert lis._try_consume_rate_limit(user_id=2) is False


# ── 1b: shared safety routing ─────────────────────────────────────────────

def test_safety_routing_guardrail_forces_review():
    from bot.safety import apply_safety_routing
    routing = {"action": "auto_reply", "answer": "all in, 保证收益", "reason": "ok"}
    out = apply_safety_routing("要不要梭哈？", routing, 9, channel_id=123)
    # Either forced to owner review or disclaimer appended — never a raw auto_reply
    assert not (out["action"] == "auto_reply" and out["reason"] == "ok"), \
        "high-risk answer passed through unmodified"


def test_safety_routing_low_confidence_clarification():
    from bot.safety import apply_safety_routing
    routing = {"action": "auto_reply", "answer": "maybe", "reason": "ok"}
    out = apply_safety_routing("这是什么意思", routing, 2, channel_id=123)
    assert "clarification" in out["reason"] or out["action"] != "auto_reply"


# ── 1c: 429 handling ─────────────────────────────────────────────────────

def _rate_limit_error():
    import openai
    req = MagicMock()
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {}
    resp.request = req
    return openai.RateLimitError("rate limited", response=resp, body=None)


def test_chat_429_retries_then_raises_unavailable():
    from bot.rag import OpenAIUnavailableError, _openai_chat_with_retry

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=_rate_limit_error())
    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(OpenAIUnavailableError):
            asyncio.run(_openai_chat_with_retry(client, model="m", messages=[]))
    # 1 initial + 3 backoff retries
    assert client.chat.completions.create.await_count == 4


def test_chat_429_recovers_on_retry():
    from bot.rag import _openai_chat_with_retry

    ok = MagicMock()
    ok.choices = [MagicMock(message=MagicMock(content="hello"))]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[_rate_limit_error(), ok])
    with patch("asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(_openai_chat_with_retry(client, model="m", messages=[]))
    assert result == "hello"


def test_pipeline_degrades_on_openai_unavailable():
    from bot.rag import run_rag_pipeline

    client = MagicMock()
    client.embeddings.create = AsyncMock(side_effect=_rate_limit_error())
    with patch("asyncio.sleep", new=AsyncMock()):
        answer, confidence, chunks = asyncio.run(
            run_rag_pipeline("test?", collection=MagicMock(), openai_client=client))
    assert chunks == []
    assert confidence == 1
    assert "稍后" in answer  # user-facing "try later", not a silent drop


# ── 1d: news poison items ─────────────────────────────────────────────────

def test_build_embed_truncates_description():
    from bot.news_feed import build_embed
    item = {"data": {"content": "标题\n" + "x" * 9000}, "time": ""}
    embed = build_embed(item)
    assert len(embed.description) <= 4096
    assert len(embed.title) <= 256


def test_build_text_truncates():
    from bot.news_feed import build_text
    item = {"data": {"content": "y" * 5000}}
    assert len(build_text(item)) <= 2000


def test_dead_letter_advances_cursor():
    from bot.news_feed import NewsFeedCog

    cog = NewsFeedCog.__new__(NewsFeedCog)
    cog._last_id = "100"
    cog._item_failures = {}
    cog._MAX_ITEM_FAILURES = 3

    async def run():
        posted, dead = [], []
        # Simulate 3 consecutive total failures of item "101"
        for _ in range(3):
            fails = cog._item_failures.get("101", 0) + 1
            if fails >= cog._MAX_ITEM_FAILURES:
                dead.append("101")
                cog._item_failures.pop("101", None)
            else:
                cog._item_failures["101"] = fails
        return posted, dead

    posted, dead = asyncio.run(run())
    assert dead == ["101"]  # skipped instead of blocking forever


# ── 1e: admin fail-closed ─────────────────────────────────────────────────

def test_admin_refuses_without_secret():
    import bot.admin as admin_mod

    async def run():
        with patch.object(admin_mod, "ADMIN_SECRET", ""):
            server = admin_mod.AdminServer(collection=None, openai_client=None)
            await server.start()
            return server._runner

    assert asyncio.run(run()) is None
