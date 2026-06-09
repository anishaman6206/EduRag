"""
GET /history — fetch the recent chat history for a user.

Pulls from Supabase chat_messages. Returns the N most recent
messages, newest first.
"""

from __future__ import annotations
import logging

from fastapi import APIRouter, HTTPException, Query

from models.response_models import HistoryItem
from services.supabase_service import get_chat_history

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/history", response_model=list[HistoryItem])
async def get_history(
    user_id: str = Query(..., min_length=1, max_length=128, description="User identifier"),
    limit: int = Query(default=50, ge=1, le=200, description="Max messages to return"),
) -> list[HistoryItem]:
    """
    Return the most recent N chat messages for `user_id`, newest first.

    Returns an empty list (not 404) if the user has no history yet.
    """
    try:
        rows = await get_chat_history(user_id=user_id, limit=limit)
    except Exception as e:
        logger.exception("get_chat_history failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Chat history temporarily unavailable.",
        )

    return [
        HistoryItem(
            id=str(r.get("id", "")),
            user_id=r.get("user_id", user_id),
            class_level=r.get("class_level"),
            subject=r.get("subject"),
            chapter_key=r.get("chapter_key"),
            query=r.get("query", ""),
            answer=r.get("answer", ""),
            sources=r.get("sources"),
            created_at=r.get("created_at"),
        )
        for r in rows
    ]
