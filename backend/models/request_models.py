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

    The student can optionally pre-filter by subject + class. If both
    are provided, the classifier uses them as hints (and is more
    likely to agree). If neither is provided, the classifier decides
    everything from the query.
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The student's free-form question.",
    )
    class_level: Optional[Literal["7", "8", "9", "10"]] = Field(
        default=None,
        description="Pre-filter by class. If omitted, the classifier decides.",
    )
    subject: Optional[Literal["math", "physics", "chemistry"]] = Field(
        default=None,
        description="Pre-filter by subject. If omitted, the classifier decides.",
    )
    user_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Stable id for chat history. Defaults to 'anonymous' if not provided.",
    )

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        return v


class HistoryQuery(BaseModel):
    """
    Query params for GET /history.

    `user_id` is required; `limit` is optional.
    """
    user_id: str = Field(..., min_length=1, max_length=128)
    limit: int = Field(default=50, ge=1, le=200)
