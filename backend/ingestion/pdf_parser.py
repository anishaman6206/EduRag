"""
PDF parser.

Uses PyMuPDF (fitz) to extract:
  - Page text (with page numbers)
  - Embedded images (raw bytes + bounding boxes)
  - Figure captions (regex over the page text)

Returns a ParsedDocument that the chunker + diagram_processor consume.

Why this design:
- We process pages independently so a bad page doesn't break the whole
  ingest. Each page is wrapped in try/except.
- We don't OCR images here — the vision LLM does that during diagram
  processing. PyMuPDF gives us the raw embedded raster, which is
  usually higher quality than an OCR-derived version.
- We capture ~200 chars of text on each side of an image's position
  on the page so the diagram processor has the surrounding context
  (caption, body text) without needing to re-walk the page.
"""

from __future__ import annotations
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


# Regex matches "Fig. 1.2: a circuit diagram", "Figure 3 — title",
# "Diagram 2.1: ..." — and the NCERT style "1.2" alone. Case-insensitive.
_FIGURE_CAPTION_RE = re.compile(
    r"""
    (?<![A-Za-z])                                    # not part of a word
    (?:Fig\.|Figure|Diagram)\s*                      # caption prefix
    (?P<num>\d+(?:\.\d+)?)                           # 1, 1.2, 2.10, etc.
    \s*[:\-–—]?\s*                         # optional : or - separator
    (?P<caption>[^\n.]{3,200}?)                      # the caption text
    (?:\.|\n|$)                                      # ends with . or newline
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ─────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class PageData:
    page_number: int                  # 1-indexed (matches what the user sees in the PDF)
    text: str                         # full text of the page
    image_rects: list[dict] = field(default_factory=list)  # for debugging / debugging


@dataclass
class DiagramCandidate:
    """An embedded image we found, before vision processing."""
    image_bytes: bytes
    bbox: tuple[float, float, float, float]   # x0, y0, x1, y1 in PDF coordinates
    page_number: int
    surrounding_text: str            # ~200 chars before + the caption + ~200 chars after
    caption: str | None = None        # regex-extracted caption if found


@dataclass
class ParsedDocument:
    pages: list[PageData] = field(default_factory=list)
    diagrams: list[DiagramCandidate] = field(default_factory=list)
    raw_text: str = ""               # concatenated page text, for convenience
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────
def _surrounding_text(page: fitz.Page, rect: fitz.Rect, char_window: int = 200) -> str:
    """
    Get up to `char_window` characters of page text that fall outside
    the image's bounding box, on both sides vertically. This is the
    caption + body text the student sees around the figure.
    """
    page_height = page.rect.height
    above = page.get_text("text", clip=fitz.Rect(0, 0, page.rect.width, rect.y0)).strip()
    below = page.get_text("text", clip=fitz.Rect(0, rect.y1, page.rect.width, page_height)).strip()
    # Take the last `char_window` chars above and first `char_window` below
    above_tail = above[-char_window:] if len(above) > char_window else above
    below_head = below[:char_window] if len(below) > char_window else below
    return f"{above_tail}\n[FIGURE]\n{below_head}".strip()


def _detect_caption(text: str) -> str | None:
    """Regex-search page text for a figure caption. Returns the first match."""
    m = _FIGURE_CAPTION_RE.search(text)
    if m:
        return f"Fig. {m.group('num')}: {m.group('caption').strip()}"
    return None


def _extract_image_bytes(page: fitz.Page, xref: int) -> bytes:
    """Pull the raw image bytes out of a PDF xref. Returns PNG bytes."""
    img = page.parent.extract_image(xref)
    return img["image"]


# ─────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────
def parse_pdf(pdf_path: str, metadata: dict[str, Any] | None = None) -> ParsedDocument:
    """
    Parse a chapter PDF into text + diagram candidates.

    Args:
        pdf_path: Absolute path to the PDF file.
        metadata: Optional dict to attach to the ParsedDocument
                  (chapter_key, subject, class_level, etc.). The pipeline
                  passes this from NAMESPACE_MAP.

    Returns:
        ParsedDocument with pages, diagrams, and concatenated raw_text.
    """
    metadata = metadata or {}
    doc = ParsedDocument(metadata=dict(metadata))

    try:
        pdf = fitz.open(pdf_path)
    except Exception as e:
        raise RuntimeError(f"Failed to open PDF {pdf_path}: {e}") from e

    try:
        for page_index in range(len(pdf)):
            page_num = page_index + 1  # 1-indexed for the user
            try:
                page = pdf[page_index]
                text = page.get_text("text")
            except Exception as e:
                logger.warning("Failed to read page %d of %s: %s", page_num, pdf_path, e)
                continue

            page_data = PageData(page_number=page_num, text=text)
            doc.pages.append(page_data)
            doc.raw_text += text + "\n"

            # Find embedded images on this page
            try:
                image_list = page.get_images(full=True)
            except Exception as e:
                logger.warning("Failed to get images on page %d: %s", page_num, e)
                continue

            for img_info in image_list:
                xref = img_info[0]
                try:
                    img_bytes = _extract_image_bytes(page, xref)
                except Exception as e:
                    logger.debug("Skipping image xref=%d on page %d: %s", xref, page_num, e)
                    continue

                # Skip tiny images (likely icons, bullets, page numbers)
                if len(img_bytes) < 1024:
                    continue

                # Find the image's bounding box on the page
                bbox = None
                try:
                    for rect in page.get_image_rects(xref):
                        # take the first one (image can be repeated)
                        bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
                        break
                except Exception:
                    bbox = None

                if bbox is None:
                    # Image exists but no rect — skip rather than guess
                    logger.debug("No rect for image xref=%d on page %d", xref, page_num)
                    continue

                # Get the surrounding text using the bounding box
                rect = fitz.Rect(*bbox)
                surround = _surrounding_text(page, rect)
                caption = _detect_caption(text)

                doc.diagrams.append(DiagramCandidate(
                    image_bytes=img_bytes,
                    bbox=bbox,
                    page_number=page_num,
                    surrounding_text=surround,
                    caption=caption,
                ))
                page_data.image_rects.append({"xref": xref, "bbox": bbox})

        logger.info(
            "Parsed %s: %d pages, %d diagram candidates, %d chars",
            pdf_path, len(doc.pages), len(doc.diagrams), len(doc.raw_text),
        )
    finally:
        pdf.close()

    return doc
