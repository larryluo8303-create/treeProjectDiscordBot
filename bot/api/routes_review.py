"""Review queue API routes — list, approve, edit, reject pending messages."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from bot.api.auth import get_current_user
from bot.api.server import get_bot, get_collection, get_openai_client
from bot.review_queue import review_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/review", tags=["review"])


class EditBody(BaseModel):
    answer: str


@router.get("/pending")
async def get_pending(_user: str = Depends(get_current_user)) -> dict:
    """Return all pending review items."""
    items = review_queue.get_pending()
    return {"count": len(items), "items": [i.to_dict() for i in items]}


@router.get("/all")
async def get_all(limit: int = 50, _user: str = Depends(get_current_user)) -> dict:
    """Return all review items (any status)."""
    items = review_queue.get_all(limit=limit)
    return {"count": len(items), "items": [i.to_dict() for i in items]}


@router.get("/{item_id}")
async def get_item(item_id: str, _user: str = Depends(get_current_user)) -> dict:
    """Return a single review item."""
    item = review_queue.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item.to_dict()


@router.post("/{item_id}/approve")
async def approve_item(item_id: str, _user: str = Depends(get_current_user)) -> dict:
    """Approve a pending review item and post the answer to Discord."""
    item = review_queue.approve(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found or already reviewed")

    # Post the approved answer to Discord
    await _post_answer_to_discord(item.channel_id, item.message_id, item.final_answer)

    # Auto-learn the Q&A pair
    await _learn_qa(item.question, item.final_answer)

    # Broadcast update
    from bot.api.ws import ws_manager
    await ws_manager.broadcast({
        "type": "review_resolved",
        "item_id": item_id,
        "action": "approved",
    })

    return {"status": "approved", "item": item.to_dict()}


@router.post("/{item_id}/edit")
async def edit_item(item_id: str, body: EditBody, _user: str = Depends(get_current_user)) -> dict:
    """Edit and approve a pending review item with a custom answer."""
    if not body.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")

    item = review_queue.edit(item_id, body.answer.strip())
    if not item:
        raise HTTPException(status_code=404, detail="Item not found or already reviewed")

    # Post the edited answer to Discord
    await _post_answer_to_discord(item.channel_id, item.message_id, item.final_answer)

    # Auto-learn the edited Q&A pair
    await _learn_qa(item.question, item.final_answer)

    # Store as negative sample (original draft was rejected in favor of edit)
    from bot.review import _store_negative_sample
    _store_negative_sample(item.question, item.draft_answer)

    # Broadcast update
    from bot.api.ws import ws_manager
    await ws_manager.broadcast({
        "type": "review_resolved",
        "item_id": item_id,
        "action": "edited",
    })

    return {"status": "edited", "item": item.to_dict()}


@router.post("/{item_id}/reject")
async def reject_item(item_id: str, _user: str = Depends(get_current_user)) -> dict:
    """Reject a pending review item."""
    item = review_queue.reject(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found or already reviewed")

    # Store as negative sample
    from bot.review import _store_negative_sample
    _store_negative_sample(item.question, item.draft_answer)

    # Broadcast update
    from bot.api.ws import ws_manager
    await ws_manager.broadcast({
        "type": "review_resolved",
        "item_id": item_id,
        "action": "rejected",
    })

    return {"status": "rejected", "item": item.to_dict()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _post_answer_to_discord(channel_id: int, message_id: int, answer: str) -> None:
    """Reply to the original Discord message with the approved/edited answer."""
    import discord

    bot = get_bot()
    if not bot:
        logger.warning("Cannot post to Discord — bot reference not set")
        return

    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)

        try:
            original_msg = await channel.fetch_message(message_id)
            await original_msg.reply(
                answer[:2000],
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.NotFound:
            await channel.send(
                answer[:2000],
                allowed_mentions=discord.AllowedMentions.none(),
            )

        logger.info("Posted review answer to channel %d", channel_id)
    except Exception as exc:
        logger.error("Failed to post review answer to Discord: %s", exc)


async def _learn_qa(question: str, answer: str) -> None:
    """Embed and store the Q&A pair in ChromaDB for future retrieval."""
    import hashlib

    from bot.config import EMBEDDING_MODEL

    collection = get_collection()
    openai_client = get_openai_client()
    if not collection or not openai_client:
        return

    qa_text = f"Q: {question}\nA: {answer}"
    doc_id = "review_" + hashlib.sha256(qa_text.encode()).hexdigest()[:16]

    try:
        resp = await openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[qa_text],
        )
        embedding = resp.data[0].embedding
        await collection.upsert(
            ids=[doc_id],
            documents=[qa_text],
            embeddings=[embedding],
            metadatas=[{"type": "qa_pair", "source": "app_review"}],
        )
        logger.info("Learned Q&A pair from app review: %s", doc_id)
    except Exception as exc:
        logger.warning("Failed to learn Q&A from app review: %s", exc)
