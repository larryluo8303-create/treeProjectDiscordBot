"""Owner review interface — DM with approve / edit / reject buttons."""

import json
import logging
import os
import re
import time

import discord
import openai

from bot.config import EMBEDDING_MODEL, OWNER_USER_ID
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

# Discord modal TextInput paragraph hard cap.
MODAL_TEXT_MAX = 4000

# Persistent component IDs for the owner review buttons. Fixed custom_ids
# + timeout=None + bot.add_view() at startup keep the buttons working
# across bot restarts: Discord re-delivers the interaction to the
# registered template view, which rebuilds its state from the review
# queue (see ReviewView._resolve). Before this, the view lived only in
# the memory of the process that sent the DM (1h timeout), so any
# restart silently killed every pending Approve / Edit / Reject button.
REVIEW_APPROVE_CUSTOM_ID = "review:approve"
REVIEW_EDIT_CUSTOM_ID = "review:edit"
REVIEW_REJECT_CUSTOM_ID = "review:reject"

# ── Negative sample storage ──────────────────────────────────────────────────

NEGATIVE_SAMPLES_FILE = data_path(os.getenv("NEGATIVE_SAMPLES_FILE", "data/negative_samples.json"))
_MAX_NEGATIVE_SAMPLES = 50  # keep only the most recent


def _store_negative_sample(question: str, bad_answer: str) -> None:
    """Append a rejected Q&A pair to the negative samples file."""
    if not question:
        return
    samples = load_negative_samples()
    samples.append({
        "question": question[:500],
        "bad_answer": bad_answer[:500],
        "timestamp": time.time(),
    })
    # Keep only the most recent samples
    samples = samples[-_MAX_NEGATIVE_SAMPLES:]
    try:
        atomic_json_write(NEGATIVE_SAMPLES_FILE, samples, ensure_ascii=False, indent=2)
        logger.info("Stored negative sample (total=%d)", len(samples))
    except OSError as exc:
        logger.warning("Failed to save negative sample: %s", exc)


def load_negative_samples() -> list[dict]:
    """Load negative samples from disk."""
    try:
        with open(NEGATIVE_SAMPLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _sync_review_queue(message_id: int, status: str, final_answer: str = "") -> None:
    """Keep the app review queue in sync with Discord DM review actions."""
    try:
        from bot.review_queue import review_queue
        review_queue.resolve_by_message_id(message_id, status, final_answer)
    except Exception as exc:
        logger.debug("Failed to sync review queue for message %s: %s", message_id, exc)


class EditAnswerModal(discord.ui.Modal, title="Edit draft answer"):
    """Modal pre-filled with the draft so the owner can tweak it inline."""

    answer = discord.ui.TextInput(
        label="Answer",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=MODAL_TEXT_MAX,
    )

    def __init__(self, parent_view: "ReviewView"):
        super().__init__()
        self.parent_view = parent_view
        # Pre-fill with the draft (truncated to modal limit).
        self.answer.default = (parent_view.draft_answer or "")[:MODAL_TEXT_MAX]

    async def on_submit(self, interaction: discord.Interaction):
        edited = (self.answer.value or "").strip()
        if not edited:
            await interaction.response.send_message(
                "Empty answer — nothing posted. You can press Edit again.",
                ephemeral=True,
            )
            return

        self.parent_view.handled = True
        try:
            await self.parent_view.original_message.reply(
                edited,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await interaction.response.edit_message(
                content="✅ **Edited answer posted.**",
                embed=None,
                view=None,
            )
            try:
                from bot.feedback_learning import record_gap_question
                question = (self.parent_view.original_message.content or "").strip()
                if question:
                    record_gap_question(question, source="owner_edited_reply")
            except Exception:
                pass
            await self.parent_view._learn_qa(edited)
            _sync_review_queue(
                self.parent_view.original_message.id,
                "edited",
                edited,
            )
            self.parent_view.stop()
        except Exception as exc:
            self.parent_view.handled = False  # allow retry
            logger.error("Failed to post edited answer: %s", exc)
            if interaction.response.is_done():
                await interaction.followup.send(f"Failed to post: {exc}", ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"Failed to post: {exc}", ephemeral=True
                )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        self.parent_view.handled = False
        logger.exception("Edit modal error: %s", error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"Edit failed: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"Edit failed: {error}", ephemeral=True
                )
        except Exception:
            pass


def _find_review_item(message_id: int):
    """Look up a review-queue item by original message id (any status)."""
    try:
        from bot.review_queue import review_queue
        for item in review_queue.get_all(limit=100000):
            if item.message_id == message_id:
                return item
    except Exception as exc:
        logger.debug("Review queue lookup failed for %s: %s", message_id, exc)
    return None


def _original_message_id_from_dm(dm_message) -> int | None:
    """Extract the original message id from a review DM's Link field."""
    try:
        for embed in (dm_message.embeds or []):
            for field in embed.fields:
                if field.name == "Link" and field.value:
                    match = re.search(r"(\d{17,20})\)?$", field.value.strip())
                    if match:
                        return int(match.group(1))
    except Exception:
        pass
    return None


class ReviewView(discord.ui.View):
    """Discord UI view with Approve / Edit / Reject buttons.

    Persistent: fixed custom_ids and no timeout. Per-message instances
    carry their state in memory; a stateless template instance
    registered via bot.add_view() at startup catches interactions for
    DMs sent by a previous bot process (e.g. after a restart) and
    rebuilds state from the review queue.
    """

    def __init__(
        self,
        original_message: discord.Message | None,
        draft_answer: str,
        bot: discord.Client,
        collection=None,
        openai_client=None,
    ):
        super().__init__(timeout=None)
        self.original_message = original_message
        self.draft_answer = draft_answer
        self.bot = bot
        self.collection = collection
        self.openai_client = openai_client
        self.handled = False

    @property
    def _is_template(self) -> bool:
        return self.original_message is None

    async def _resolve(self, interaction: discord.Interaction) -> "ReviewView | None":
        """Return a stateful view for this interaction.

        Per-message instances return themselves. The startup template
        instance rebuilds state from the review queue (keyed by the
        original message id embedded in the DM's Link field). Returns
        None after replying when the draft can no longer be acted on.
        """
        if not self._is_template:
            return self
        original_id = _original_message_id_from_dm(interaction.message)
        if original_id is None:
            await interaction.response.send_message(
                "无法定位这条草稿的原始消息，按钮已失效。", ephemeral=True
            )
            return None
        item = _find_review_item(original_id)
        if item is None:
            await interaction.response.send_message(
                "这条草稿已不在待审队列里（可能已过期）。", ephemeral=True
            )
            return None
        if item.status != "pending":
            await interaction.response.send_message("Already handled.", ephemeral=True)
            return None
        try:
            channel = self.bot.get_channel(item.channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(item.channel_id)
            original = await channel.fetch_message(item.message_id)
        except Exception as exc:
            logger.error(
                "Failed to rebuild review state for message %s: %s", original_id, exc
            )
            await interaction.response.send_message(
                "原始消息已无法读取（可能已被删除）。", ephemeral=True
            )
            return None
        return ReviewView(
            original,
            item.draft_answer,
            self.bot,
            collection=self.collection,
            openai_client=self.openai_client,
        )

    async def _learn_qa(self, answer: str) -> None:
        """Store the question + approved/edited answer as a Q&A pair in ChromaDB."""
        if not self.collection or not self.openai_client:
            return
        question = (self.original_message.content or "").strip()
        answer = answer.strip()
        if not question or not answer:
            return

        qa_text = f"Q: {question}\nA: {answer}"
        doc_id = f"review_{self.original_message.id}"

        try:
            existing = await self.collection.get(ids=[doc_id], include=[])
            if existing["ids"]:
                return

            try:
                response = await self.openai_client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=[qa_text],
                )
            except (openai.APITimeoutError, openai.APIConnectionError) as first_err:
                logger.warning("Embedding API error (%s) on review — retrying once",
                               type(first_err).__name__)
                response = await self.openai_client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=[qa_text],
                )
            embedding = response.data[0].embedding

            await self.collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[qa_text],
                metadatas=[{
                    "type": "qa_pair",
                    "source": "owner_review",
                    "channel_id": str(self.original_message.channel.id),
                    "message_id": str(self.original_message.id),
                    "author_id": str(self.original_message.author.id),
                    "timestamp": self.original_message.created_at.isoformat(),
                }],
            )
            logger.info("Auto-learned from review: message %s (%d chars)",
                        self.original_message.id, len(qa_text))
        except Exception as exc:
            logger.error("Failed to auto-learn from review: %s", exc)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅", custom_id=REVIEW_APPROVE_CUSTOM_ID)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = await self._resolve(interaction)
        if view is not None:
            await view._do_approve(interaction)

    async def _do_approve(self, interaction: discord.Interaction):
        if self.handled:
            await interaction.response.send_message("Already handled.", ephemeral=True)
            return
        self.handled = True
        try:
            await self.original_message.reply(
                self.draft_answer,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await interaction.response.edit_message(
                content="✅ **Approved and posted.**",
                embed=None,
                view=None,
            )
            await self._learn_qa(self.draft_answer)
            _sync_review_queue(
                self.original_message.id,
                "approved",
                self.draft_answer,
            )
        except Exception as exc:
            self.handled = False  # allow retry
            logger.error("Failed to post approved answer: %s", exc)
            if interaction.response.is_done():
                await interaction.followup.send(f"Failed to post: {exc}", ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"Failed to post: {exc}", ephemeral=True
                )
            return
        self.stop()

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.blurple, emoji="✏️", custom_id=REVIEW_EDIT_CUSTOM_ID)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = await self._resolve(interaction)
        if view is not None:
            await view._do_edit(interaction)

    async def _do_edit(self, interaction: discord.Interaction):
        if self.handled:
            await interaction.response.send_message("Already handled.", ephemeral=True)
            return
        # Open a modal pre-filled with the draft so the owner can tweak it
        # instead of retyping the whole answer. `handled` flips on submit.
        await interaction.response.send_modal(EditAnswerModal(self))

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, emoji="❌", custom_id=REVIEW_REJECT_CUSTOM_ID)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = await self._resolve(interaction)
        if view is not None:
            await view._do_reject(interaction)

    async def _do_reject(self, interaction: discord.Interaction):
        if self.handled:
            await interaction.response.send_message("Already handled.", ephemeral=True)
            return
        self.handled = True
        await interaction.response.edit_message(
            content="❌ **Rejected. No reply sent.**",
            embed=None,
            view=None,
        )
        # Store as negative sample for future prompt guidance
        _store_negative_sample(
            question=(self.original_message.content or "").strip(),
            bad_answer=self.draft_answer.strip(),
        )
        _sync_review_queue(self.original_message.id, "rejected")
        self.stop()

    async def on_timeout(self) -> None:
        if not self.handled:
            logger.info("Review timed out for message %s", self.original_message.id)


async def send_for_review(
    bot: discord.Client,
    original_message: discord.Message,
    draft_answer: str,
    confidence: int,
    context_snippets: list[dict] | None = None,
    collection=None,
    openai_client=None,
) -> None:
    """DM the owner with the question, draft answer, and review buttons."""
    if not OWNER_USER_ID:
        # Misconfigured deployment — don't silently drop the review request.
        # Log loudly and tell the user their question was recorded.
        logger.error("OWNER_USER_ID is not set — cannot forward message %s for review",
                     getattr(original_message, "id", "?"))
        try:
            await original_message.reply(
                "你的问题已记录，频道主稍后会来人工回复。",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception:
            pass
        return
    try:
        owner = await bot.fetch_user(OWNER_USER_ID)
    except Exception as exc:
        logger.error("Failed to fetch owner user (ID=%s): %s", OWNER_USER_ID, exc)
        try:
            await original_message.reply(
                "你的问题已记录，频道主稍后会来人工回复。",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception:
            pass
        return
    if not owner:
        logger.error("Could not fetch owner user (ID=%s) — returned falsy", OWNER_USER_ID)
        try:
            await original_message.reply(
                "你的问题已记录，频道主稍后会来人工回复。",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception:
            pass
        return

    # Build embed
    embed = discord.Embed(
        title="Review Required",
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="Channel",
        value=f"<#{original_message.channel.id}>",
        inline=True,
    )
    embed.add_field(
        name="Asked by",
        value=f"{original_message.author.display_name} ({original_message.author})",
        inline=True,
    )
    embed.add_field(
        name="Confidence",
        value=f"{confidence}/10",
        inline=True,
    )

    # Truncate question for embed
    question_text = original_message.content[:1000]
    embed.add_field(
        name="Question",
        value=question_text or "(no text)",
        inline=False,
    )
    embed.add_field(
        name="Draft Answer",
        value=draft_answer[:1000],
        inline=False,
    )

    # Add context snippets if available
    if context_snippets:
        snippets_text = "\n".join(
            f"- {s.get('text', '')[:120]}..." for s in context_snippets[:3]
        )
        embed.add_field(
            name="Top Context",
            value=snippets_text[:1000],
            inline=False,
        )

    # Add link to original message
    if hasattr(original_message, "jump_url"):
        embed.add_field(
            name="Link",
            value=f"[Jump to message]({original_message.jump_url})",
            inline=False,
        )

    view = ReviewView(original_message, draft_answer, bot,
                       collection=collection, openai_client=openai_client)

    try:
        await owner.send(embed=embed, view=view)
        logger.info(
            "Sent review DM for message %s (confidence=%d)",
            original_message.id,
            confidence,
        )
    except discord.Forbidden:
        logger.error("Cannot DM owner — DMs may be disabled")
    except Exception as exc:
        logger.error("Failed to send review DM: %s", exc)


async def notify_owner_auto_reply(
    bot: discord.Client,
    original_message: discord.Message,
    reply_text: str,
    confidence: int,
) -> None:
    """DM the owner a notification that the bot auto-replied (no action needed)."""
    if not OWNER_USER_ID:
        return
    try:
        owner = await bot.fetch_user(OWNER_USER_ID)
    except Exception as exc:
        logger.error("Could not fetch owner user (ID=%s): %s", OWNER_USER_ID, exc)
        return
    if not owner:
        logger.warning("notify_owner_auto_reply: fetch_user(%s) returned falsy — skipping", OWNER_USER_ID)
        return

    embed = discord.Embed(
        title="🤖 自动回复通知",
        description="机器人已自动回复以下消息（无需操作）",
        color=discord.Color.green(),
    )
    embed.add_field(
        name="频道",
        value=f"<#{original_message.channel.id}>",
        inline=True,
    )
    embed.add_field(
        name="提问者",
        value=f"{original_message.author.display_name} ({original_message.author})",
        inline=True,
    )
    embed.add_field(
        name="置信度",
        value=f"{confidence}/10",
        inline=True,
    )

    question_text = (original_message.content or "").strip()[:1000] or "(无文字 / 图片消息)"
    embed.add_field(name="问题", value=question_text, inline=False)
    embed.add_field(name="自动回复", value=reply_text[:1000], inline=False)

    if hasattr(original_message, "jump_url"):
        embed.add_field(
            name="链接",
            value=f"[跳转到消息]({original_message.jump_url})",
            inline=False,
        )

    try:
        await owner.send(embed=embed)
        logger.info(
            "Sent auto-reply notification DM for message %s (confidence=%d)",
            original_message.id,
            confidence,
        )
    except discord.Forbidden:
        logger.error("Cannot DM owner for auto-reply notification — DMs may be disabled")
    except Exception as exc:
        logger.error("Failed to send auto-reply notification DM: %s", exc)
