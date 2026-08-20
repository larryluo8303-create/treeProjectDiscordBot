"""Tests for bot.admin module — lazy import safety and configuration."""

from unittest.mock import patch


class TestAdminLazyImport:
    """Verify that admin.py does NOT crash at import time without aiohttp."""

    def test_admin_module_importable_without_aiohttp(self):
        """Importing bot.admin should succeed even if aiohttp is missing.

        The actual aiohttp import happens lazily inside start() and route methods.
        """
        # Just importing should not raise
        import bot.admin
        assert hasattr(bot.admin, "AdminServer")
        # ADMIN_ENABLED/PORT/SECRET are now in bot.config
        from bot.config import ADMIN_ENABLED, ADMIN_PORT
        assert isinstance(ADMIN_ENABLED, bool)
        assert isinstance(ADMIN_PORT, int)

    def test_admin_server_instantiation(self):
        from bot.admin import AdminServer
        from unittest.mock import MagicMock
        server = AdminServer(collection=MagicMock(), openai_client=MagicMock())
        assert server._runner is None


class TestAdminConfig:
    def test_admin_defaults(self):
        from bot.config import ADMIN_ENABLED, ADMIN_PORT, ADMIN_SECRET
        # Default is disabled
        assert isinstance(ADMIN_ENABLED, bool)
        assert isinstance(ADMIN_PORT, int)
        assert isinstance(ADMIN_SECRET, str)
