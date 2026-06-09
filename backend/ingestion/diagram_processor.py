"""
Diagram processor.

⚠️  VISION IS A STUB IN THIS BUILD.

The project owner decided to skip vision for now — gpt-4o-mini is
used for all text, and the plan is to add a vision-capable model
later. This module therefore does the things we CAN do without
vision:

  1. Filter the diagram candidates from pdf_parser to keep only
     genuinely-meaningful figures (drop icons, page headers,
     decorations, very small images).
  2. Extract a "description" from the surrounding text + caption.
     This is what gets embedded for search.
  3. Build a metadata record (url, caption, page, chapter) for the
     chunk we'll upsert to Pinecone.

When vision is added, replace `_build_diagram_description` with a
call to a vision-capable model (gpt-4o with image input, or
similar) and parse the DIAGRAM_DESCRIPTION_PROMPT JSON output.
The public surface (process_diagram) stays the same so the
pipeline doesn't have to change.

Why a stub instead of nothing:
  - The retriever's design assumes diagram chunks have a `text`
    field that's queryable. Without this stub, the pipeline has
    no way to populate that text, and the diagram path silently
    breaks in retrieval.
  - With the stub, diagrams are indexed and retrievable based on
    their caption + surrounding text, which is a reasonable
    approximation for the "no vision" build.
"""

from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass

from config.constants import DIAGRAM_DESCRIPTION_PROMPT
from ingestion.pdf_parser import DiagramCandidate

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Thresholds — tuned to NCERT PDFs
#
# Real NCERT pages have:
#   - Page header / footer logos (~1-3 KB)            → drop
#   - Decorative dividers, bullet icons (~2-5 KB)     → drop
#   - Inline activity images (~5-15 KB)               → drop (not a "diagram")
#   - Actual textbook figures (15 KB - 2 MB)          → KEEP
#
# We additionally cap how many diagrams we keep per page to
# avoid the "same figure rendered at multiple resolutions"
# problem common in PDF extraction.
# ─────────────────────────────────────────────────────────────────────────
MIN_IMAGE_BYTES = 15_000         # below this is almost always an icon/divider
MAX_IMAGE_BYTES = 8_000_000      # above this is probably a full-page photo
MAX_DIAGRAMS_PER_PAGE = 4        # if more, keep the largest N (decoration noise)


# ─────────────────────────────────────────────────────────────────────────
# Result data class
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class DiagramResult:
    """A diagram ready to be upserted as a chunk in Pinecone."""
    # Pinecone-side
    chunk_id: str
    description: str                 # the text we'll embed
    chapter_key: str
    class_level: str
    subject: str
    page: int
    caption: str | None

    # Source side
    image_bytes: bytes
    image_hash: str

    # Metadata for the UI (not used for embedding)
    storage_path: str                # where the image would go in Supabase Storage
    public_url: str | None           # populated after Supabase upload


# ─────────────────────────────────────────────────────────────────────────
# Filtering
# ─────────────────────────────────────────────────────────────────────────
def _looks_meaningful(candidate: DiagramCandidate) -> bool:
    """
    Heuristic: keep only images that are likely textbook figures.
    Drops page headers, page numbers, footer logos, decorative bullets.
    """
    size = len(candidate.image_bytes)
    if size < MIN_IMAGE_BYTES or size > MAX_IMAGE_BYTES:
        return False
    return True


def dedupe_per_page(results: list[DiagramResult]) -> list[DiagramResult]:
    """
    Public helper: after filtering, if a single page has many
    "diagrams" (often the same image rendered at multiple sizes,
    or 5 small activity icons), keep only the largest N per page.

    Caller (the pipeline) invokes this once after collecting all
    DiagramResult objects from process_diagram.
    """
    by_page: dict[int, list[DiagramResult]] = {}
    for r in results:
        by_page.setdefault(r.page, []).append(r)

    kept: list[DiagramResult] = []
    for page, items in by_page.items():
        if len(items) <= MAX_DIAGRAMS_PER_PAGE:
            kept.extend(items)
        else:
            items_sorted = sorted(items, key=lambda r: len(r.image_bytes), reverse=True)
            kept.extend(items_sorted[:MAX_DIAGRAMS_PER_PAGE])
    return kept


# ─────────────────────────────────────────────────────────────────────────
# Description builder (STUB)
# ─────────────────────────────────────────────────────────────────────────
def _build_diagram_description(
    candidate: DiagramCandidate,
    chapter_key: str,
    chapter_name: str,
    class_level: str,
    subject: str,
) -> str:
    """
    Build a queryable text description of a diagram WITHOUT calling a
    vision model. Uses the caption (if any) and surrounding page text.

    Format:
        Figure caption: <caption or "no caption">
        Page: <n>
        Chapter: <chapter_name>
        Context: <surrounding text, truncated>

    When vision is added, replace this with a real call to a vision
    model — the input is `candidate.image_bytes` and the output is
    a JSON object per DIAGRAM_DESCRIPTION_PROMPT.
    """
    parts: list[str] = []
    if candidate.caption:
        parts.append(f"Caption: {candidate.caption}")
    else:
        parts.append("Caption: (no caption detected)")

    parts.append(f"Chapter: {chapter_name}")
    parts.append(f"Page: {candidate.page_number}")
    parts.append(f"Subject: {subject}, Class {class_level}")

    # Use surrounding text as a stand-in for actual visual description
    surround = candidate.surrounding_text.strip()
    if surround:
        # Trim to ~500 chars to keep the embedding focused
        if len(surround) > 500:
            surround = surround[:500] + "…"
        parts.append(f"Context: {surround}")

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────
async def process_diagram(
    candidate: DiagramCandidate,
    *,
    chapter_key: str,
    chapter_name: str,
    class_level: str,
    subject: str,
    storage_bucket: str = "diagrams",
    supabase_url: str | None = None,
) -> DiagramResult | None:
    """
    Process a single DiagramCandidate.

    Returns None if the diagram is filtered out (too small, decorative).
    Otherwise returns a DiagramResult with a description ready to
    embed, plus the raw image bytes + storage path for upload.
    """
    if not _looks_meaningful(candidate):
        return None

    image_hash = hashlib.sha256(candidate.image_bytes).hexdigest()[:12]
    storage_path = (
        f"{subject}/class_{class_level}/{chapter_key}/"
        f"fig_{candidate.page_number}_{image_hash}.png"
    )
    # The public URL is None here — the pipeline uploads to Supabase
    # Storage AFTER this returns and patches the URL back in.
    public_url = None

    description = _build_diagram_description(
        candidate,
        chapter_key=chapter_key,
        chapter_name=chapter_name,
        class_level=class_level,
        subject=subject,
    )

    chunk_id = f"{chapter_key}_d_{candidate.page_number}_{image_hash}"

    return DiagramResult(
        chunk_id=chunk_id,
        description=description,
        chapter_key=chapter_key,
        class_level=class_level,
        subject=subject,
        page=candidate.page_number,
        caption=candidate.caption,
        image_bytes=candidate.image_bytes,
        image_hash=image_hash,
        storage_path=storage_path,
        public_url=public_url,
    )
