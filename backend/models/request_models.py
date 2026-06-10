"""
Pydantic request models.

These define the shape of incoming JSON. Validation happens at the
FastAPI layer, so handlers can trust their inputs.
"""

from __future__ import annotations
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from config.constants import ALL_SUBJECTS, ALL_CLASSES


class AskRequest(BaseModel):
    """
    Body for POST /ask.

    The student can optionally pre-filter by subject + class. The
    refiner handles multilingual queries (Hinglish, Hindi, etc.) and
    the answer is generated in the same language the student used.

    Multi-turn support: pass `conversation_id` to group messages
    into the same conversation thread. The backend will fetch the
    last N prior turns for that user and prepend them to the
    generator prompt so the LLM has context for follow-up questions
    like "explain step 2".
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The student's free-form question.",
    )
    class_level: Optional[Literal["8", "9", "10"]] = Field(
        default=None,
        description="Pre-filter by class. If omitted, the dense retriever "
                    "fans out across all 39 namespaces.",
    )
    subject: Optional[Literal["math", "physics", "chemistry", "biology"]] = Field(
        default=None,
        description="Pre-filter by subject. If omitted, the dense retriever "
                    "fans out across all 39 namespaces.",
    )
    chapter_key: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Pin to a specific chapter (e.g. 'physics_8_ch4'). "
                    "If set, overrides class+subject filters and the retriever "
                    "searches only that chapter's namespace.",
    )
    user_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Stable id for chat history. Defaults to 'anonymous' if not provided.",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Stable id for the conversation thread. If provided, the "
                    "last N prior turns in this conversation are prepended "
                    "to the generator prompt for multi-turn context.",
    )
    # Optional explicit history for clients that manage their own
    # conversation state on the client side and don't want the
    # backend to fetch from Supabase. If both this and
    # conversation_id are provided, this takes precedence.
    history: Optional[list["ChatTurn"]] = Field(
        default=None,
        description="Explicit chat history. Overrides conversation_id lookup.",
    )

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        return v


class ChatTurn(BaseModel):
    """One prior turn in a multi-turn conversation."""
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)


# Resolve the forward reference (history is list[ChatTurn])
AskRequest.model_rebuild()


class HistoryQuery(BaseModel):
    """
    Query params for GET /history.

    `user_id` is required; `limit` is optional.
    """
    user_id: str = Field(..., min_length=1, max_length=128)
    limit: int = Field(default=50, ge=1, le=200)
    conversation_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Optional — only return messages from this conversation thread.",
    )
