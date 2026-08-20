"""Promo and Lesson scheduling API routes."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from bot.api.auth import get_current_user
from bot.scheduler import (
    add_promo, list_promos, cancel_promo,
    add_lesson, list_lessons, cancel_lesson,
)

_ET = ZoneInfo("America/New_York")

router = APIRouter(prefix="/api", tags=["promo"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class PromoCreate(BaseModel):
    title: str
    description: str
    scheduled_at: str  # ISO format or "YYYY-MM-DD HH:MM"
    channel_ids: list[int] = []
    url: str = ""


class LessonCreate(BaseModel):
    title: str
    content: str
    scheduled_at: str
    channel_ids: list[int] = []
    repeat: str = "none"  # none | daily | weekly


# ---------------------------------------------------------------------------
# Promos
# ---------------------------------------------------------------------------
@router.get("/promos")
async def get_promos(_user: str = Depends(get_current_user)) -> dict:
    """List all scheduled promos."""
    promos = list_promos()
    return {"count": len(promos), "items": promos}


@router.post("/promos")
async def create_promo(body: PromoCreate, _user: str = Depends(get_current_user)) -> dict:
    """Create a new scheduled promo."""
    try:
        scheduled_at = datetime.fromisoformat(body.scheduled_at)
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=_ET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format. Use ISO format.")

    if not body.channel_ids:
        from bot.config import PROMO_CHANNEL_IDS
        channel_ids = list(PROMO_CHANNEL_IDS)
    else:
        channel_ids = body.channel_ids

    if not channel_ids:
        raise HTTPException(status_code=400, detail="No channel IDs configured.")

    promo = add_promo(
        title=body.title,
        description=body.description,
        scheduled_at=scheduled_at,
        channel_ids=channel_ids,
        created_by=0,
        url=body.url,
    )
    return {"status": "created", "promo": promo}


@router.delete("/promos/{promo_id}")
async def delete_promo(promo_id: str, _user: str = Depends(get_current_user)) -> dict:
    """Cancel a scheduled promo."""
    ok = cancel_promo(promo_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Promo not found or already posted.")
    return {"status": "cancelled", "id": promo_id}


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------
@router.get("/lessons")
async def get_lessons(_user: str = Depends(get_current_user)) -> dict:
    """List all scheduled lessons."""
    lessons = list_lessons()
    return {"count": len(lessons), "items": lessons}


@router.post("/lessons")
async def create_lesson(body: LessonCreate, _user: str = Depends(get_current_user)) -> dict:
    """Create a new scheduled lesson."""
    try:
        scheduled_at = datetime.fromisoformat(body.scheduled_at)
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=_ET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format.")

    if not body.channel_ids:
        from bot.config import PROMO_CHANNEL_IDS
        channel_ids = list(PROMO_CHANNEL_IDS)
    else:
        channel_ids = body.channel_ids

    if not channel_ids:
        raise HTTPException(status_code=400, detail="No channel IDs configured.")

    lesson = add_lesson(
        title=body.title,
        content=body.content,
        scheduled_at=scheduled_at,
        channel_ids=channel_ids,
        created_by=0,
        repeat=body.repeat,
    )
    return {"status": "created", "lesson": lesson}


@router.delete("/lessons/{lesson_id}")
async def delete_lesson(lesson_id: str, _user: str = Depends(get_current_user)) -> dict:
    """Cancel a scheduled lesson."""
    ok = cancel_lesson(lesson_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Lesson not found or already posted.")
    return {"status": "cancelled", "id": lesson_id}
