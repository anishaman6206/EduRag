"""
Pydantic response models.

These shape what the API returns for non-streaming endpoints
(/history, /health). The streaming /ask endpoint uses raw SSE
events (see rag/generator.py) rather than these models, because
the events flow incrementally and the client assembles them.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    """Per-service liveness check result."""
    status: str = Field(..., description="'ok' or 'error'")
    detail: Optional[str] = Field(default=None, description="Error message if status is 'error'")


class HealthResponse(BaseModel):
    """Top-level /health response."""
    status: str = Field(..., description="'ok' if all checks pass, 'degraded' otherwise")
    checks: dict[str, HealthCheck] = Field(default_factory=dict)


class SourceChunk(BaseModel):
    """A retrieved chunk citation shown in the answer card."""
    chunk_id: str
    chapter_key: str
    page: Optional[int] = None
    score: float
    preview: str


class HistoryItem(BaseModel):
    """One row from the chat_messages table, returned by /history."""
    id: str
    user_id: str
    class_level: Optional[str] = None
    subject: Optional[str] = None
    chapter_key: Optional[str] = None
    query: str
    answer: str
    sources: Optional[list[dict[str, Any]]] = None
    created_at: datetime
