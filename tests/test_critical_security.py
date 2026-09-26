"""Regression tests for the 4 critical security/stability fixes.

1. Path traversal in serve_spa (bot/api/server.py)
2. Fail-closed API credentials (bot/config.py + bot/api/server.py)
3. Webhook fail-open (bot/webhook.py)
4. Scheduler exception isolation (bot/scheduler.py)
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ── Critical 1: path traversal ─────────────────────────────────────────────
class TestSpaPathTraversal:
    def test_traversal_blocked(self, tmp_path):
        from bot.api.server import _resolve_spa_file

        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html></html>")

        with pytest.raises(HTTPException) as exc_info:
            _resolve_spa_file(str(dist), "../../../../etc/passwd")
        assert exc_info.value.status_code == 404

    def test_traversal_encoded_blocked(self, tmp_path):
        from bot.api.server import _resolve_spa_file

        dist = tmp_path / "dist"
        dist.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("topsecret")
        # normpath collapses "sub/../.." back to dist, but "....//" style and
        # nested ".." must never resolve outside dist
        with pytest.raises(HTTPException):
            _resolve_spa_file(str(dist), "..%2F..%2Fsecret.txt".replace("%2F", "/"))
        # direct check: resolved path must stay inside dist
        with pytest.raises(HTTPException):
            _resolve_spa_file(str(dist), "../secret.txt")

    def test_legit_file_served(self, tmp_path):
        from bot.api.server import _resolve_spa_file

        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        asset = dist / "assets" / "app.js"
        asset.write_text("console.log(1)")
        assert _resolve_spa_file(str(dist), "assets/app.js") == str(asset)

    def test_missing_file_returns_none(self, tmp_path):
        from bot.api.server import _resolve_spa_file

        dist = tmp_path / "dist"
        dist.mkdir()
        assert _resolve_spa_file(str(dist), "nope.js") is None
        assert _resolve_spa_file(str(dist), "") is None

    def test_dotdot_inside_dist_ok(self, tmp_path):
        from bot.api.server import _resolve_spa_file

        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        asset = dist / "assets" / "app.js"
        asset.write_text("x")
        # "a/../b" stays inside dist after normalization — allowed
        assert _resolve_spa_file(str(dist), "assets/../assets/app.js") == str(asset)


# ── Critical 2: fail-closed API credentials ────────────────────────────────
class TestApiFailClosed:
    def test_create_app_rejects_missing_username(self):
        from bot.api.server import create_app

        with patch("bot.api.server.API_USERNAME", ""), \
             patch("bot.api.server.API_PASSWORD", "pw"), \
             patch("bot.api.server.API_SECRET_KEY", "x" * 32):
            with pytest.raises(RuntimeError, match="API_USERNAME"):
                create_app()

    def test_create_app_rejects_missing_password(self):
        from bot.api.server import create_app

        with patch("bot.api.server.API_USERNAME", "u"), \
             patch("bot.api.server.API_PASSWORD", ""), \
             patch("bot.api.server.API_SECRET_KEY", "x" * 32):
            with pytest.raises(RuntimeError, match="API_PASSWORD"):
                create_app()

    def test_create_app_rejects_short_secret(self):
        from bot.api.server import create_app

        with patch("bot.api.server.API_USERNAME", "u"), \
             patch("bot.api.server.API_PASSWORD", "pw"), \
             patch("bot.api.server.API_SECRET_KEY", "short"):
            with pytest.raises(RuntimeError, match="API_SECRET_KEY"):
                create_app()

    def test_create_app_rejects_default_secret(self):
        """The old hardcoded default must never be accepted."""
        from bot.api.server import create_app

        with patch("bot.api.server.API_USERNAME", "u"), \
             patch("bot.api.server.API_PASSWORD", "pw"), \
             patch("bot.api.server.API_SECRET_KEY", "change-me-in-production"):
            with pytest.raises(RuntimeError):
                create_app()

    def test_config_has_no_default_credentials(self):
        # Import fresh with empty env to prove there are no insecure defaults.
        import importlib

        with patch.dict(os.environ, {}, clear=False):
            for key in ("API_USERNAME", "API_PASSWORD", "API_SECRET_KEY"):
                os.environ.pop(key, None)
            import bot.config as cfg
            importlib.reload(cfg)
        try:
            assert cfg.API_USERNAME == ""
            assert cfg.API_PASSWORD == ""
            assert cfg.API_SECRET_KEY == ""
        finally:
            importlib.reload(cfg)


# ── Critical 3: webhook fail-closed ─────────────────────────────────────────
class FakeRequest:
    def __init__(self, body: bytes, headers=None):
        self._body = body
        self.headers = headers or {}

    async def read(self):
        return self._body


def _make_server():
    from bot.webhook import WebhookServer

    return WebhookServer(collection=MagicMock(), openai_client=MagicMock())


class TestWebhookFailClosed:
    async def test_rejects_when_secret_not_configured(self):
        srv = _make_server()
        with patch("bot.webhook.WEBHOOK_SECRET", ""):
            resp = await srv._handle_ingest(FakeRequest(b'{"text": "hello world"}'))
        assert resp.status == 503

    async def test_rejects_bad_signature(self):
        import hashlib, hmac

        srv = _make_server()
        body = b'{"text": "hello world, this is long enough"}'
        with patch("bot.webhook.WEBHOOK_SECRET", "s3cret"), \
             patch("bot.webhook.WEBHOOK_MAX_BODY_BYTES", 1024 * 1024), \
             patch("bot.webhook.WEBHOOK_MAX_ITEMS", 50):
            resp = await srv._handle_ingest(
                FakeRequest(body, {"X-Webhook-Signature": "wrong"})
            )
        assert resp.status == 403

    async def test_rejects_oversized_body(self):
        srv = _make_server()
        with patch("bot.webhook.WEBHOOK_SECRET", "s3cret"), \
             patch("bot.webhook.WEBHOOK_MAX_BODY_BYTES", 10):
            resp = await srv._handle_ingest(FakeRequest(b"x" * 11))
        assert resp.status == 413

    async def test_rejects_too_many_items(self):
        import json as _json

        srv = _make_server()
        items = [{"text": "long enough text item %d" % i} for i in range(5)]
        body = _json.dumps(items).encode()
        sig = __import__("hmac").new(b"s3cret", body, __import__("hashlib").sha256).hexdigest()
        with patch("bot.webhook.WEBHOOK_SECRET", "s3cret"), \
             patch("bot.webhook.WEBHOOK_MAX_ITEMS", 2):
            resp = await srv._handle_ingest(
                FakeRequest(body, {"X-Webhook-Signature": sig})
            )
        assert resp.status == 413


# ── Critical 4: scheduler exception isolation ──────────────────────────────
class TestSchedulerIsolation:
    async def test_one_failing_subtask_does_not_kill_loop(self):
        import bot.scheduler as sched

        cog = sched.SchedulerCog(MagicMock())
        calls = []

        async def ok(name):
            async def _inner(now):
                calls.append(name)
            return _inner

        async def boom(now):
            calls.append("reminders")
            raise RuntimeError("simulated failure")

        with patch.object(sched, "PROMO_ENABLED", False), \
             patch.object(sched, "FEATURE_SLA_MONITORING", False), \
             patch.object(cog, "_process_reminders", side_effect=boom), \
             patch.object(cog, "_process_faq_push", side_effect=lambda now: calls.append("faq_push")), \
             patch.object(cog, "_process_learning_gap_report", side_effect=lambda now: calls.append("gap")):
            # one iteration of the 60s loop — must not raise
            await cog._check_scheduled()

        assert "reminders" in calls  # the failing one ran
        assert "faq_push" in calls   # the ones after it still ran
        assert "gap" in calls
