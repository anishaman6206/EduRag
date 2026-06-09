"""
GET /history — fetch chat history.

Three query modes:
  1. No conversation_id:  Returns the N most recent messages
     across all of the user's conversations.
  2. With conversation_id: Returns the N most recent messages
     from that specific conversation.
  3. mode=conversations:   Returns a summary list of the user's
     conversation threads (one row per conversation, with
     first_query, last_message_at, message_count). This is what
     the frontend history sidebar uses.
"""

from __future__ import annotations
import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from models.response_models import HistoryItem
from services.supabase_service import (
    get_chat_history,
    list_conversations,
    get_messages_by_conversation,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class ConversationSummary(BaseModel):
    """One conversation thread — used by the frontend history sidebar."""
    conversation_id: str
    first_query: str
    last_message_at: str
    message_count: int


@router.get("/history", response_model=list[HistoryItem] | list[ConversationSummary])
async def get_history(
    user_id: str = Query(..., min_length=1, max_length=128, description="User identifier"),
    limit: int = Query(default=50, ge=1, le=200, description="Max messages to return"),
    conversation_id: Optional[str] = Query(
        default=None,
        max_length=128,
        description="Restrict to a specific conversation thread.",
    ),
    mode: Literal["messages", "conversations"] = Query(
        default="messages",
        description="'messages' (default) returns chat rows; 'conversations' "
                    "returns a summary of each conversation thread.",
    ),
):
    """
    Fetch chat history. Mode 'messages' returns full chat_messages
    rows. Mode 'conversations' returns one ConversationSummary per
    conversation thread, sorted by most-recent activity.
    """
    try:
        if mode == "conversations":
            rows = await list_conversations(user_id=user_id, limit=limit)
            return [
                ConversationSummary(
                    conversation_id=r["conversation_id"],
                    first_query=r["first_query"],
                    last_message_at=r["last_message_at"],
                    message_count=r["message_count"],
                )
                for r in rows
            ]

        # mode == "messages"
        if conversation_id:
            rows = await get_messages_by_conversation(
                user_id=user_id, conversation_id=conversation_id,
            )
        else:
            rows = await get_chat_history(user_id=user_id, limit=limit)
    except Exception as e:
        logger.exception("get_history failed: %s", e)
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
