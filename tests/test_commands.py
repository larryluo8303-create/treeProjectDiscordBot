"""Tests for bot.commands module — helper functions and cog instantiation."""

from unittest.mock import MagicMock

import pytest

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


class TestAskCooldown:
    """Cost firewall: /ask must be per-user rate limited (30s)."""

    def _interaction(self, user_id: int):
        from datetime import datetime, timezone

        interaction = MagicMock()
        interaction.user.id = user_id
        interaction.created_at = datetime.now(timezone.utc)
        return interaction

    def test_ask_has_cooldown_check(self):
        # The cooldown decorator registers exactly one check predicate.
        assert len(BotCommands.ask_cmd.checks) == 1

    @pytest.mark.asyncio
    async def test_cooldown_allows_first_call(self):
        pred = BotCommands.ask_cmd.checks[0]
        assert await pred(self._interaction(424201)) is True

    @pytest.mark.asyncio
    async def test_cooldown_blocks_immediate_second_call(self):
        import discord

        pred = BotCommands.ask_cmd.checks[0]
        interaction = self._interaction(424202)
        assert await pred(interaction) is True
        with pytest.raises(discord.app_commands.CommandOnCooldown):
            await pred(interaction)

    @pytest.mark.asyncio
    async def test_cooldown_error_handler_sends_chinese_message(self):
        import discord

        cog = BotCommands.__new__(BotCommands)
        interaction = MagicMock()
        interaction.user.id = 424203
        interaction.response.is_done.return_value = False
        cooldown = MagicMock()
        error = discord.app_commands.CommandOnCooldown(cooldown, 12.3)

        await BotCommands.ask_cmd_error(cog, interaction, error)

        interaction.response.send_message.assert_called_once()
        sent_text = interaction.response.send_message.call_args[0][0]
        assert "问得太快了" in sent_text
