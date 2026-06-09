"""
Ingestion orchestrator.

Coordinates the full PDF → Pinecone path:

  1. parse_pdf() — extract text + diagram candidates
  2. create_chunks() — semantic parent/child chunks
  3. embed children (batched) + diagrams
  4. upload diagram images to Supabase Storage (skip in dev)
  5. upsert children (and diagram chunks) to Pinecone
  6. save parents to Supabase (Postgres)

All steps log progress. On failure, the pipeline rolls back the
Pinecone namespace (so re-running is safe) and surfaces a clear
error.

Idempotency:
  - Child chunk IDs are deterministic:
    {chapter_key}_{idx}_{parent_content_hash[:8]}
  - Parent chunk IDs are deterministic: p_{content_hash[:8]}
  - Diagram chunk IDs are deterministic:
    {chapter_key}_d_{page}_{image_hash}
  Re-ingesting a chapter overwrites — no duplicates.
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from config.constants import get_chapter_meta, NAMESPACE_MAP
from config.settings import get_settings
from services.pinecone_service import upsert_vectors, delete_namespace
from services.supabase_service import save_parent_chunk, upload_diagram

from ingestion.pdf_parser import parse_pdf
from ingestion.chunker import create_chunks, ChildChunk, ParentChunk
from ingestion.embedder import embed_texts
from ingestion.diagram_processor import process_diagram, DiagramResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Summary returned to the caller (CLI / API)
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class IngestionSummary:
    chapter_key: str
    namespace: str
    parents_created: int
    children_upserted: int
    diagrams_found: int
    diagrams_kept: int
    diagrams_uploaded: int
    vectors_upserted: int
    duration_seconds: float
    errors: list[str]


# ─────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────
async def run_ingestion(
    pdf_path: str,
    chapter_key: str,
    *,
    upload_diagrams_to_storage: bool = False,   # opt-in; default off in dev
    namespace: str | None = None,
    rollback_on_failure: bool = True,
) -> IngestionSummary:
    """
    Ingest a single chapter PDF into the EduRag system.

    Args:
        pdf_path: Absolute path to the chapter PDF.
        chapter_key: Must exist in NAMESPACE_MAP.
        upload_diagrams_to_storage: If True, upload diagram images to
            Supabase Storage and write the public URL into the chunk
            metadata. Off by default — most dev work doesn't need it,
            and it adds a network call per diagram.
        namespace: Override the Pinecone namespace (rare; defaults to
            the one in NAMESPACE_MAP for this chapter_key).
        rollback_on_failure: If True and the pipeline fails midway,
            delete the namespace so the next run is clean. Default
            True — safer for the bulk-ingest case.

    Returns:
        IngestionSummary with counts and any errors.
    """
    import time
    t0 = time.monotonic()
    errors: list[str] = []

    # ── Validate chapter
    if chapter_key not in NAMESPACE_MAP:
        raise KeyError(f"Unknown chapter_key '{chapter_key}'")
    meta = NAMESPACE_MAP[chapter_key]
    target_namespace = namespace or meta["namespace"]

    metadata = {
        "chapter_key": chapter_key,
        "class_level": meta["class_level"],
        "subject": meta["subject"],
        "namespace": target_namespace,
        "display_name": meta["display_name"],
    }

    logger.info("=== Ingesting %s → namespace '%s' ===", chapter_key, target_namespace)

    # ── Step 1: parse the PDF
    logger.info("[1/5] Parsing PDF: %s", pdf_path)
    parsed = parse_pdf(pdf_path, metadata=metadata)
    logger.info("       %d pages, %d diagram candidates, %d chars",
                len(parsed.pages), len(parsed.diagrams), len(parsed.raw_text))

    # ── Step 2: chunk
    logger.info("[2/5] Chunking (semantic parent/child)")
    parents, children = await create_chunks(parsed, metadata)
    logger.info("       %d parents, %d children", len(parents), len(children))

    # ── Step 3: embed children (batched) + diagram descriptions
    logger.info("[3/5] Embedding children + diagrams")
    child_texts = [c.text for c in children]
    child_vectors = await embed_texts(child_texts) if child_texts else []

    # Process diagrams in parallel with child embedding? No — diagrams
    # are CPU-light (just filtering + text building), so do them inline.
    diagram_results: list[DiagramResult] = []
    for d in parsed.diagrams:
        result = await process_diagram(
            d,
            chapter_key=chapter_key,
            chapter_name=meta["display_name"],
            class_level=meta["class_level"],
            subject=meta["subject"],
        )
        if result is not None:
            diagram_results.append(result)
    logger.info("       %d diagram chunks kept out of %d candidates",
                len(diagram_results), len(parsed.diagrams))

    diagram_descriptions = [r.description for r in diagram_results]
    diagram_vectors = await embed_texts(diagram_descriptions) if diagram_descriptions else []

    # ── Step 4: upload diagram images to Supabase Storage (optional)
    diagrams_uploaded = 0
    if upload_diagrams_to_storage and diagram_results:
        logger.info("[4/5] Uploading diagram images to Supabase Storage")
        try:
            for d in diagram_results:
                url = await upload_diagram(
                    storage_path=d.storage_path,
                    image_bytes=d.image_bytes,
                )
                d.public_url = url
                diagrams_uploaded += 1
        except Exception as e:
            errors.append(f"Diagram upload failed: {e}")
            logger.warning("Continuing without diagram URLs: %s", e)
    else:
        logger.info("[4/5] Skipping diagram upload (upload_diagrams_to_storage=False)")

    # ── Step 5: upsert children + diagrams to Pinecone, save parents to Supabase
    logger.info("[5/5] Upserting vectors to Pinecone '%s'", target_namespace)
    try:
        # Build child vectors
        child_payloads = [
            {
                "id": c.id,
                "values": child_vectors[i],
                "metadata": _child_metadata(c),
            }
            for i, c in enumerate(children)
        ]

        # Build diagram vectors
        diagram_payloads = [
            {
                "id": d.chunk_id,
                "values": diagram_vectors[i],
                "metadata": _diagram_metadata(d),
            }
            for i, d in enumerate(diagram_results)
        ]

        all_payloads = child_payloads + diagram_payloads
        if all_payloads:
            await upsert_vectors(target_namespace, all_payloads)
        logger.info("       Upserted %d vectors (%d children + %d diagrams)",
                    len(all_payloads), len(child_payloads), len(diagram_payloads))
    except Exception as e:
        errors.append(f"Pinecone upsert failed: {e}")
        logger.exception("Pinecone upsert failed")
        if rollback_on_failure:
            logger.warning("Rolling back namespace '%s'", target_namespace)
            try:
                await delete_namespace(target_namespace)
            except Exception as rb:
                errors.append(f"Rollback also failed: {rb}")
        raise

    # Save parent chunks to Supabase. We do this AFTER the vector
    # upsert so that if Supabase fails, the vectors are still queryable
    # (just without parent context). Supabase failure is non-fatal.
    try:
        for p in parents:
            await save_parent_chunk(_parent_record(p))
        logger.info("       Saved %d parent chunks to Supabase", len(parents))
    except Exception as e:
        errors.append(f"Supabase save failed: {e}")
        logger.warning("Continuing without Supabase parent storage: %s", e)

    elapsed = time.monotonic() - t0
    summary = IngestionSummary(
        chapter_key=chapter_key,
        namespace=target_namespace,
        parents_created=len(parents),
        children_upserted=len(children),
        diagrams_found=len(parsed.diagrams),
        diagrams_kept=len(diagram_results),
        diagrams_uploaded=diagrams_uploaded,
        vectors_upserted=len(child_payloads) + len(diagram_payloads),
        duration_seconds=round(elapsed, 2),
        errors=errors,
    )
    logger.info("=== Done in %.2fs: %s ===", elapsed, summary)
    return summary


# ─────────────────────────────────────────────────────────────────────────
# Metadata builders — keep Pinecone metadata small and typed
# ─────────────────────────────────────────────────────────────────────────
def _child_metadata(c: ChildChunk) -> dict[str, Any]:
    """Pinecone metadata for a child chunk. Strings and numbers only."""
    md = {
        "text": c.text,
        "parent_id": c.parent_id,
        "chapter_key": c.chapter_key,
        "class_level": c.class_level,
        "subject": c.subject,
        "content_type": c.content_type,
        "chunk_index": c.chunk_index,
        "token_count": c.token_count,
        "content_hash": c.metadata.get("content_hash", ""),
    }
    if c.page is not None:
        md["page"] = c.page
    return md


def _diagram_metadata(d: DiagramResult) -> dict[str, Any]:
    """Pinecone metadata for a diagram chunk."""
    return {
        "text": d.description,
        "chapter_key": d.chapter_key,
        "class_level": d.class_level,
        "subject": d.subject,
        "content_type": "diagram",
        "page": d.page,
        "caption": d.caption or "",
        "diagram_url": d.public_url or "",
        "image_hash": d.image_hash,
        "storage_path": d.storage_path,
    }


def _parent_record(p: ParentChunk) -> dict[str, Any]:
    """Supabase row for a parent chunk."""
    return {
        "id": p.id,
        "chapter_key": p.chapter_key,
        "content": p.content,
        "token_count": p.token_count,
        "content_type": p.content_type,
        "page_start": p.page_start,
        "page_end": p.page_end,
        "metadata": p.metadata,
    }
