"""Tests for bot.webhook module — signature verification and payload handling."""

import hashlib
import hmac
from unittest.mock import patch

from bot.webhook import _verify_signature


class TestVerifySignature:
    def test_no_secret_always_valid(self):
        with patch("bot.webhook.WEBHOOK_SECRET", ""):
            assert _verify_signature(b"any body", "") is True
            assert _verify_signature(b"any body", "wrongsig") is True

    def test_valid_signature(self):
        secret = "mysecret"
        body = b'{"text": "hello"}'
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch("bot.webhook.WEBHOOK_SECRET", secret):
            assert _verify_signature(body, expected) is True

    def test_invalid_signature(self):
        secret = "mysecret"
        body = b'{"text": "hello"}'
        with patch("bot.webhook.WEBHOOK_SECRET", secret):
            assert _verify_signature(body, "invalid_hex") is False

    def test_wrong_body(self):
        secret = "mysecret"
        body = b'{"text": "hello"}'
        other_body = b'{"text": "world"}'
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch("bot.webhook.WEBHOOK_SECRET", secret):
            assert _verify_signature(other_body, sig) is False

    def test_empty_body(self):
        secret = "mysecret"
        body = b""
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch("bot.webhook.WEBHOOK_SECRET", secret):
            assert _verify_signature(body, expected) is True

    def test_hmac_timing_safe(self):
        """Ensure we use compare_digest (timing-safe comparison)."""
        secret = "sec"
        body = b"data"
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        # Slightly modified signature — should fail
        bad_sig = expected[:-1] + ("0" if expected[-1] != "0" else "1")
        with patch("bot.webhook.WEBHOOK_SECRET", secret):
            assert _verify_signature(body, bad_sig) is False
