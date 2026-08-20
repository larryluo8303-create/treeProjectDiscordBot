"""Tests for the FastAPI API server."""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest


class TestAuth:
    """Test JWT authentication flow."""

    def test_login_success(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        with patch("bot.api.auth.API_USERNAME", "testuser"), \
             patch("bot.api.auth.API_PASSWORD", "testpass"), \
             patch("bot.api.auth._hashed_password") as mock_hash:
            # We need to re-hash for the test
            from passlib.context import CryptContext
            pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
            mock_hash.__str__ = lambda _: pwd_ctx.hash("testpass")

            app = create_app()
            client = TestClient(app)

            # Use the actual password verification
            with patch("bot.api.auth.pwd_context") as mock_pwd_ctx:
                mock_pwd_ctx.verify.return_value = True
                resp = client.post("/api/auth/login", data={
                    "username": "testuser",
                    "password": "testpass",
                })
                assert resp.status_code == 200
                data = resp.json()
                assert "access_token" in data
                assert data["token_type"] == "bearer"
                assert data["expires_in"] > 0

    def test_login_failure(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        resp = client.post("/api/auth/login", data={
            "username": "wrong",
            "password": "wrong",
        })
        assert resp.status_code == 401

    def test_protected_route_no_token(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        resp = client.get("/api/stats")
        assert resp.status_code == 401


class TestHealthEndpoint:
    """Test the /api/health endpoint (no auth required)."""

    def test_health(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data
        assert "timestamp" in data


class TestTokenCreation:
    """Test JWT token creation and validation."""

    def test_create_and_verify_token(self):
        from bot.api.auth import _create_access_token, get_current_user

        token = _create_access_token({"sub": "testuser"})
        assert isinstance(token, str)

        # Should successfully extract username
        username = get_current_user(token)
        assert username == "testuser"

    def test_invalid_token_raises(self):
        from fastapi import HTTPException
        from bot.api.auth import get_current_user

        with pytest.raises(HTTPException):
            get_current_user("invalid.token.here")


class TestReviewQueue:
    """Test the review queue data structure."""

    def test_add_and_get_pending(self):
        from bot.review_queue import ReviewQueue

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp_path = f.name

        with patch("bot.review_queue.REVIEW_QUEUE_FILE", tmp_path):
            q = ReviewQueue()
            assert q.pending_count == 0

            item = q.add(
                channel_id=123,
                channel_name="test-channel",
                message_id=456,
                author_name="TestUser",
                author_id=789,
                question="What is X?",
                draft_answer="X is...",
                confidence=6,
            )
            assert q.pending_count == 1
            assert item.status == "pending"

            pending = q.get_pending()
            assert len(pending) == 1
            assert pending[0].question == "What is X?"

        os.unlink(tmp_path)

    def test_approve(self):
        from bot.review_queue import ReviewQueue

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp_path = f.name

        with patch("bot.review_queue.REVIEW_QUEUE_FILE", tmp_path):
            q = ReviewQueue()
            item = q.add(
                channel_id=1, channel_name="ch", message_id=2,
                author_name="u", author_id=3, question="Q",
                draft_answer="A", confidence=5,
            )
            result = q.approve(item.id)
            assert result is not None
            assert result.status == "approved"
            assert result.final_answer == "A"
            assert q.pending_count == 0

        os.unlink(tmp_path)

    def test_edit(self):
        from bot.review_queue import ReviewQueue

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp_path = f.name

        with patch("bot.review_queue.REVIEW_QUEUE_FILE", tmp_path):
            q = ReviewQueue()
            item = q.add(
                channel_id=1, channel_name="ch", message_id=2,
                author_name="u", author_id=3, question="Q",
                draft_answer="A", confidence=5,
            )
            result = q.edit(item.id, "Better answer")
            assert result is not None
            assert result.status == "edited"
            assert result.final_answer == "Better answer"

        os.unlink(tmp_path)

    def test_reject(self):
        from bot.review_queue import ReviewQueue

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp_path = f.name

        with patch("bot.review_queue.REVIEW_QUEUE_FILE", tmp_path):
            q = ReviewQueue()
            item = q.add(
                channel_id=1, channel_name="ch", message_id=2,
                author_name="u", author_id=3, question="Q",
                draft_answer="A", confidence=5,
            )
            result = q.reject(item.id)
            assert result is not None
            assert result.status == "rejected"
            assert q.pending_count == 0

        os.unlink(tmp_path)

    def test_persistence(self):
        from bot.review_queue import ReviewQueue

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp_path = f.name

        with patch("bot.review_queue.REVIEW_QUEUE_FILE", tmp_path):
            q1 = ReviewQueue()
            q1.add(
                channel_id=1, channel_name="ch", message_id=2,
                author_name="u", author_id=3, question="Q",
                draft_answer="A", confidence=5,
            )
            assert q1.pending_count == 1

            # Create a new queue instance — should load from file
            q2 = ReviewQueue()
            assert q2.pending_count == 1

        os.unlink(tmp_path)

    def test_double_action_returns_none(self):
        from bot.review_queue import ReviewQueue

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([], f)
            tmp_path = f.name

        with patch("bot.review_queue.REVIEW_QUEUE_FILE", tmp_path):
            q = ReviewQueue()
            item = q.add(
                channel_id=1, channel_name="ch", message_id=2,
                author_name="u", author_id=3, question="Q",
                draft_answer="A", confidence=5,
            )
            q.approve(item.id)
            # Second action on same item should return None
            assert q.approve(item.id) is None
            assert q.edit(item.id, "X") is None
            assert q.reject(item.id) is None

        os.unlink(tmp_path)


class TestWSManager:
    """Test WebSocket connection manager."""

    def test_verify_ws_token_valid(self):
        from bot.api.auth import _create_access_token
        from bot.api.ws import _verify_ws_token

        token = _create_access_token({"sub": "admin"})
        assert _verify_ws_token(token) is True

    def test_verify_ws_token_invalid(self):
        from bot.api.ws import _verify_ws_token

        assert _verify_ws_token("invalid") is False
        assert _verify_ws_token("") is False


class TestPublicAPI:
    """Test public client-facing API routes."""

    def test_public_faq(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            resp = client.get("/api/public/faq")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "count" in data

    def test_public_faq_disabled(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", False):
            resp = client.get("/api/public/faq")
            assert resp.status_code == 404

    def test_public_faq_bad_api_key(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", "secret123"):
            # No key
            resp = client.get("/api/public/faq")
            assert resp.status_code == 403

            # Wrong key
            resp = client.get("/api/public/faq", headers={"x-api-key": "wrong"})
            assert resp.status_code == 403

            # Correct key
            resp = client.get("/api/public/faq", headers={"x-api-key": "secret123"})
            assert resp.status_code == 200

    def test_public_chat_empty_message(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            resp = client.post("/api/public/chat", json={"message": ""})
            assert resp.status_code == 400

    def test_public_chat_too_long(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            resp = client.post("/api/public/chat", json={"message": "x" * 2001})
            assert resp.status_code == 400

    def test_public_kb_search_empty(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            resp = client.get("/api/public/kb/search", params={"q": ""})
            assert resp.status_code == 400

    def test_public_promos(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            resp = client.get("/api/public/promos")
            assert resp.status_code == 200
            assert "items" in resp.json()

    def test_public_lessons(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            resp = client.get("/api/public/lessons")
            assert resp.status_code == 200
            assert "items" in resp.json()

    def test_rate_limit(self):
        from bot.api.routes_public import _request_log, _rate_limit

        # Clear rate limit state
        _request_log.clear()

        # Create a mock request
        mock_request = MagicMock()
        mock_request.client.host = "test-rate-limit-ip"

        # Fill up the rate limit
        with patch("bot.api.routes_public.CLIENT_RATE_LIMIT_PER_MINUTE", 3):
            _rate_limit(mock_request)  # 1
            _rate_limit(mock_request)  # 2
            _rate_limit(mock_request)  # 3
            # 4th should raise
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                _rate_limit(mock_request)
            assert exc_info.value.status_code == 429

        _request_log.clear()

    def test_public_digest(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            resp = client.get("/api/public/digest")
            assert resp.status_code == 200
            data = resp.json()
            assert "total_queries" in data
            assert "top_questions" in data
            assert data["period"] == "24h"

    def test_public_lessons_archive(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            resp = client.get("/api/public/lessons/archive")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "count" in data

    def test_public_analyze_image_no_file(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            # No file provided should return 422 (validation error)
            resp = client.post("/api/public/analyze-image")
            assert resp.status_code == 422

    def test_public_analyze_image_wrong_type(self):
        from fastapi.testclient import TestClient
        from bot.api.server import create_app
        import io

        app = create_app()
        client = TestClient(app)

        with patch("bot.api.routes_public.CLIENT_API_ENABLED", True), \
             patch("bot.api.routes_public.CLIENT_API_KEY", ""):
            # Non-image file
            resp = client.post(
                "/api/public/analyze-image",
                files={"image": ("test.txt", io.BytesIO(b"not an image"), "text/plain")},
            )
            assert resp.status_code == 400
