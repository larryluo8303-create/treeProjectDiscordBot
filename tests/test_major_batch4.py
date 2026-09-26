"""Regression tests for Major batch 4 (deployment / API hardening).

- /api/auth/login is rate-limited per IP (brute-force protection)
- Public API is fail-closed by default (CLIENT_API_ENABLED defaults to false)
- API key comparison is constant-time; wrong key -> 403, disabled -> 404
- Vision endpoint has its own stricter per-IP rate limit
- Global daily budget caps OpenAI-backed public endpoints
- conversation_history is capped per message and in total
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException


def _mock_request(ip: str = "1.2.3.4"):
    return SimpleNamespace(client=SimpleNamespace(host=ip), headers={})


def test_login_rate_limit_blocks_after_max_attempts():
    import bot.api.auth as auth
    auth._login_attempts.clear()
    req = _mock_request("9.9.9.9")
    with patch.object(auth, "LOGIN_MAX_ATTEMPTS", 3), \
         patch.object(auth, "LOGIN_WINDOW_SECONDS", 300):
        for _ in range(3):
            auth._check_login_rate_limit(req)  # allowed
        with pytest.raises(HTTPException) as ei:
            auth._check_login_rate_limit(req)  # 4th -> 429
        assert ei.value.status_code == 429
    auth._login_attempts.clear()


def test_login_rate_limit_is_per_ip():
    import bot.api.auth as auth
    auth._login_attempts.clear()
    with patch.object(auth, "LOGIN_MAX_ATTEMPTS", 1), \
         patch.object(auth, "LOGIN_WINDOW_SECONDS", 300):
        auth._check_login_rate_limit(_mock_request("1.1.1.1"))
        # Different IP is unaffected
        auth._check_login_rate_limit(_mock_request("2.2.2.2"))
        with pytest.raises(HTTPException):
            auth._check_login_rate_limit(_mock_request("1.1.1.1"))
    auth._login_attempts.clear()


def test_client_api_fail_closed_default():
    """CLIENT_API_ENABLED must default to false when the env var is unset."""
    import importlib
    import bot.config as cfg
    old = os.environ.pop("CLIENT_API_ENABLED", None)
    try:
        importlib.reload(cfg)
        assert cfg.CLIENT_API_ENABLED is False
    finally:
        if old is not None:
            os.environ["CLIENT_API_ENABLED"] = old
        importlib.reload(cfg)


def test_check_api_key_disabled_returns_404():
    from bot.api import routes_public as rp
    with patch.object(rp, "CLIENT_API_ENABLED", False):
        with pytest.raises(HTTPException) as ei:
            rp._check_api_key(_mock_request())
        assert ei.value.status_code == 404


def test_check_api_key_wrong_key_returns_403():
    from bot.api import routes_public as rp
    req = _mock_request()
    req.headers = {"x-api-key": "wrong"}
    with patch.object(rp, "CLIENT_API_ENABLED", True), \
         patch.object(rp, "CLIENT_API_KEY", "correct-key"):
        with pytest.raises(HTTPException) as ei:
            rp._check_api_key(req)
        assert ei.value.status_code == 403


def test_check_api_key_correct_key_passes():
    from bot.api import routes_public as rp
    req = _mock_request()
    req.headers = {"x-api-key": "correct-key"}
    with patch.object(rp, "CLIENT_API_ENABLED", True), \
         patch.object(rp, "CLIENT_API_KEY", "correct-key"):
        assert rp._check_api_key(req) is None  # no exception


def test_vision_rate_limit_is_stricter():
    from bot.api import routes_public as rp
    rp._vision_request_log.clear()
    req = _mock_request("7.7.7.7")
    with patch.object(rp, "CLIENT_VISION_LIMIT_PER_MINUTE", 2):
        rp._vision_rate_limit(req)
        rp._vision_rate_limit(req)
        with pytest.raises(HTTPException) as ei:
            rp._vision_rate_limit(req)
        assert ei.value.status_code == 429
    rp._vision_request_log.clear()


@pytest.mark.asyncio
async def test_daily_budget_exhaustion():
    from bot.api import routes_public as rp
    async with rp._daily_usage_lock:
        rp._daily_usage["day"] = ""
        rp._daily_usage["count"] = 0
    with patch.object(rp, "CLIENT_API_DAILY_LIMIT", 2):
        await rp._check_daily_budget()
        await rp._check_daily_budget()
        with pytest.raises(HTTPException) as ei:
            await rp._check_daily_budget()
        assert ei.value.status_code == 429
    async with rp._daily_usage_lock:
        rp._daily_usage["day"] = ""
        rp._daily_usage["count"] = 0


def test_build_history_str_per_message_cap():
    from bot.api import routes_public as rp
    with patch.object(rp, "CLIENT_CHAT_HISTORY_PER_MSG_CHARS", 10), \
         patch.object(rp, "CLIENT_CHAT_HISTORY_TOTAL_CHARS", 100000):
        out = rp.build_history_str([{"role": "user", "content": "x" * 500}])
        # "用户: " prefix + 10 chars of content
        assert out == "用户: " + "x" * 10


def test_build_history_str_total_cap():
    from bot.api import routes_public as rp
    with patch.object(rp, "CLIENT_CHAT_HISTORY_PER_MSG_CHARS", 100000), \
         patch.object(rp, "CLIENT_CHAT_HISTORY_TOTAL_CHARS", 120):
        out = rp.build_history_str([
            {"role": "user", "content": "a" * 100},  # line = "用户: " + 100 chars = 104
            {"role": "user", "content": "b" * 100},
        ])
        assert len(out) <= 120
        assert "a" in out  # first message kept, second cut by total cap
        assert "b" not in out


def test_build_history_str_empty():
    from bot.api import routes_public as rp
    assert rp.build_history_str(None) == ""
    assert rp.build_history_str([]) == ""


def test_cors_defaults_to_same_origin_only():
    """CORS_ORIGINS must default to empty (no wildcard)."""
    import importlib
    import bot.config as cfg
    old = os.environ.pop("CORS_ORIGINS", None)
    try:
        importlib.reload(cfg)
        assert cfg.CORS_ORIGINS == []
    finally:
        if old is not None:
            os.environ["CORS_ORIGINS"] = old
        importlib.reload(cfg)
