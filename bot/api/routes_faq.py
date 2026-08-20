"""FAQ API routes."""

from fastapi import APIRouter, Depends

from bot.api.auth import get_current_user
from bot.api.server import get_openai_client
from bot.faq import get_cached_faq, _load_faq, generate_faq

router = APIRouter(prefix="/api/faq", tags=["faq"])


@router.get("")
async def get_faq(_user: str = Depends(get_current_user)) -> dict:
    """Return current FAQ items."""
    data = _load_faq()
    return data if data else {"items": []}


@router.post("/generate")
async def trigger_faq_generation(_user: str = Depends(get_current_user)) -> dict:
    """Trigger FAQ generation from recent high-confidence queries."""
    openai_client = get_openai_client()
    items = await generate_faq(openai_client)
    return {"items": items, "count": len(items)}
