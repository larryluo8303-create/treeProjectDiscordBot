"""Config API routes — view and update runtime configuration."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bot.api.auth import get_current_user
from bot.config import (
    CONFIDENCE_THRESHOLD,
    CONVERSATION_MEMORY_SIZE,
    CONVERSATION_MEMORY_TTL,
    EMBEDDING_MODEL,
    GLOBAL_MAX_PER_MINUTE,
    LLM_MODEL,
    OWNER_USER_ID,
    RESPOND_MODE,
    TARGET_CHANNEL_IDS,
    THREAD_AUTO_REPLY,
    THREAD_CONTEXT_MESSAGES,
    USER_COOLDOWN_SECONDS,
    VISION_MODEL,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config(_user: str = Depends(get_current_user)) -> dict:
    """Return current bot configuration snapshot."""
    return {
        "respond_mode": RESPOND_MODE,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "llm_model": LLM_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "vision_model": VISION_MODEL,
        "target_channel_ids": TARGET_CHANNEL_IDS,
        "owner_user_id": OWNER_USER_ID,
        "user_cooldown_seconds": USER_COOLDOWN_SECONDS,
        "global_max_per_minute": GLOBAL_MAX_PER_MINUTE,
        "conversation_memory_size": CONVERSATION_MEMORY_SIZE,
        "conversation_memory_ttl": CONVERSATION_MEMORY_TTL,
        "thread_auto_reply": THREAD_AUTO_REPLY,
        "thread_context_messages": THREAD_CONTEXT_MESSAGES,
    }


class ConfigPatch(BaseModel):
    """Patchable runtime config fields."""
    confidence_threshold: int | None = None
    respond_mode: str | None = None
    user_cooldown_seconds: int | None = None
    global_max_per_minute: int | None = None
    thread_auto_reply: bool | None = None
    thread_context_messages: int | None = None
    conversation_memory_size: int | None = None
    conversation_memory_ttl: int | None = None


@router.patch("")
async def patch_config(patch: ConfigPatch, _user: str = Depends(get_current_user)) -> dict:
    """Update runtime configuration (changes are NOT persisted to .env)."""
    import bot.config as cfg

    changes: dict = {}
    for field_name, value in patch.model_dump(exclude_none=True).items():
        attr = field_name.upper()
        if hasattr(cfg, attr):
            old = getattr(cfg, attr)
            setattr(cfg, attr, value)
            changes[field_name] = {"old": old, "new": value}

    # Broadcast config change via WebSocket
    if changes:
        from bot.api.ws import ws_manager
        await ws_manager.broadcast({
            "type": "config_changed",
            "changes": changes,
        })

    return {"updated": changes}
