"""
GET /chapters — list the available NCERT chapters.

The frontend uses this to populate the chapter filter dropdown. Each
chapter is identified by a stable `chapter_key` (e.g. "physics_8_ch4")
that the /ask route can accept as a hint for retrieval.

Optional query params:
  - class_level: only chapters in this class
  - subject: only chapters in this subject
"""

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from config.constants import NAMESPACE_MAP

router = APIRouter()


class ChapterInfo(BaseModel):
    chapter_key: str
    display_name: str
    class_level: str
    subject: str
    chapter_number: int


@router.get("/chapters", response_model=list[ChapterInfo])
async def list_chapters(
    class_level: Optional[str] = Query(default=None, description="e.g. '8' or '10'"),
    subject: Optional[str] = Query(default=None, description="e.g. 'physics' or 'biology'"),
):
    """Return the list of available NCERT chapters, optionally filtered."""
    out: list[ChapterInfo] = []
    for chapter_key, meta in NAMESPACE_MAP.items():
        if class_level and meta["class_level"] != class_level:
            continue
        if subject and meta["subject"] != subject:
            continue
        out.append(ChapterInfo(
            chapter_key=chapter_key,
            display_name=meta["display_name"],
            class_level=meta["class_level"],
            subject=meta["subject"],
            chapter_number=meta["chapter_number"],
        ))
    # Sort by class, then subject, then chapter_number — stable
    out.sort(key=lambda c: (c.class_level, c.subject, c.chapter_number))
    return out
