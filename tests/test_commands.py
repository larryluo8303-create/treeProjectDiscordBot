"""Tests for bot.commands module — helper functions and cog instantiation."""

from unittest.mock import MagicMock

from bot.commands import _is_owner, PromotionCommands, BotCommands


class TestIsOwner:
    def test_owner_returns_true(self):
        from bot.config import OWNER_USER_ID
        interaction = MagicMock()
        interaction.user.id = OWNER_USER_ID
        assert _is_owner(interaction) is True

    def test_non_owner_returns_false(self):
        interaction = MagicMock()
        interaction.user.id = 999999999
        assert _is_owner(interaction) is False

    def test_zero_id_non_owner(self):
        interaction = MagicMock()
        interaction.user.id = 0
        # Owner ID is unlikely 0, so this should be False
        assert _is_owner(interaction) is False


class TestCogInstantiation:
    def test_promotion_commands_init(self):
        bot = MagicMock()
        cog = PromotionCommands(bot)
        assert cog.bot is bot

    def test_bot_commands_init(self):
        bot = MagicMock()
        collection = MagicMock()
        openai_client = MagicMock()
        cog = BotCommands(bot, collection, openai_client)
        assert cog.bot is bot
        assert cog.collection is collection
        assert cog.openai_client is openai_client
