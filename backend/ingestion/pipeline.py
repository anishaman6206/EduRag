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
from services.pinecone_service import (
    upsert_vectors, delete_namespace,
    fetch_existing_hashes, delete_vectors_by_id,
    list_all_ids_in_namespace,
)
from services.supabase_service import save_parent_chunk, upload_diagram

from ingestion.pdf_parser import parse_pdf
from ingestion.chunker import create_chunks, ChildChunk, ParentChunk
from ingestion.embedder import embed_texts
from ingestion.diagram_processor import process_diagram, dedupe_per_page, DiagramResult

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
    children_added: int       # new (didn't exist before)
    children_updated: int     # existed with different version_hash
    children_unchanged: int   # existed with same version_hash — skipped
    children_deleted: int     # existed in Pinecone, not in new ingest
    diagrams_found: int
    diagrams_kept: int
    diagrams_uploaded: int
    diagrams_added: int
    diagrams_updated: int
    diagrams_unchanged: int
    diagrams_deleted: int
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

    # Dedup: if a single page produced many "diagrams" (often the same
    # image at multiple resolutions, or 5 small activity icons), keep
    # only the largest N per page.
    diagram_results = dedupe_per_page(diagram_results)

    logger.info("       %d diagram chunks kept out of %d candidates (after per-page dedup)",
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

    # ── Step 5: incremental upsert children + diagrams to Pinecone, save parents to Supabase
    #
    # Incremental logic: for each chunk, compare its version_hash to
    # the version_hash of any existing vector with the same id in
    # Pinecone. Only upsert the diff. Delete any old ids that the
    # new ingest no longer produces (e.g. chunks that got merged or
    # removed when the chunker changed).
    logger.info("[5/5] Incremental upsert to Pinecone '%s'", target_namespace)

    # Counts for the summary
    children_added = children_updated = children_unchanged = children_deleted = 0
    diagrams_added = diagrams_updated = diagrams_unchanged = diagrams_deleted = 0

    try:
        # Build new child + diagram payloads
        child_payloads = [
            {
                "id": c.id,
                "values": child_vectors[i],
                "metadata": _child_metadata(c),
            }
            for i, c in enumerate(children)
        ]
        diagram_payloads = [
            {
                "id": d.chunk_id,
                "values": diagram_vectors[i],
                "metadata": _diagram_metadata(d),
            }
            for i, d in enumerate(diagram_results)
        ]

        # Fetch existing version_hashes for both pools
        existing_child_hashes = await fetch_existing_hashes(
            target_namespace, [c.id for c in children],
        )
        existing_diagram_hashes = await fetch_existing_hashes(
            target_namespace, [d.chunk_id for d in diagram_results],
        )

        # Diff: keep only the vectors whose content actually changed
        # (or are new). Skip vectors whose version_hash matches the
        # existing one — Pinecone already has them, no work needed.
        to_upsert: list[dict] = []
        to_delete: list[str] = []

        for payload, child in zip(child_payloads, children):
            new_hash = child.metadata.get("version_hash", "")
            old_hash = existing_child_hashes.get(child.id)
            if old_hash is None:
                children_added += 1
                to_upsert.append(payload)
            elif old_hash == new_hash:
                children_unchanged += 1
            else:
                children_updated += 1
                to_upsert.append(payload)

        for payload, diagram in zip(diagram_payloads, diagram_results):
            new_hash = diagram.version_hash
            old_hash = existing_diagram_hashes.get(diagram.chunk_id)
            if old_hash is None:
                diagrams_added += 1
                to_upsert.append(payload)
            elif old_hash == new_hash:
                diagrams_unchanged += 1
            else:
                diagrams_updated += 1
                to_upsert.append(payload)

        # Find children/diagrams that existed before but no longer exist.
        #
        # Important: existing_child_hashes / existing_diagram_hashes only
        # contains IDs from the NEW ingest's candidate set, so they
        # can't tell us about stale vectors whose IDs are no longer
        # produced. We need a full enumeration of the namespace to
        # find those.
        new_child_ids = {c.id for c in children}
        new_diagram_ids = {d.chunk_id for d in diagram_results}

        # Only do the full-namespace scan if this is a "small" chapter.
        # For 1000s of vectors the list() call is still <2s on Pinecone
        # serverless, but no point scanning when nothing could possibly
        # be stale (a fresh namespace, for example).
        if existing_child_hashes or existing_diagram_hashes or len(to_upsert) == 0:
            all_existing_ids = await list_all_ids_in_namespace(target_namespace)
        else:
            all_existing_ids = list(existing_child_hashes.keys()) + list(existing_diagram_hashes.keys())

        for old_id in all_existing_ids:
            if old_id not in new_child_ids and old_id not in new_diagram_ids:
                # Only delete IDs we recognize as belonging to this chapter
                if not old_id.startswith(f"{chapter_key}_"):
                    continue
                if "_d_" in old_id:
                    diagrams_deleted += 1
                else:
                    children_deleted += 1
                to_delete.append(old_id)

        # Apply the diff
        if to_upsert:
            await upsert_vectors(target_namespace, to_upsert)
        if to_delete:
            await delete_vectors_by_id(target_namespace, to_delete)

        logger.info(
            "       Diff: +%d children, ~%d updated, =%d unchanged, -%d deleted;"
            " +%d diagrams, ~%d updated, =%d unchanged, -%d deleted."
            " Sent %d upserts, %d deletes (skipped %d unchanged).",
            children_added, children_updated, children_unchanged, children_deleted,
            diagrams_added, diagrams_updated, diagrams_unchanged, diagrams_deleted,
            len(to_upsert), len(to_delete),
            children_unchanged + diagrams_unchanged,
        )
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
        children_upserted=len(to_upsert),
        children_added=children_added,
        children_updated=children_updated,
        children_unchanged=children_unchanged,
        children_deleted=children_deleted,
        diagrams_found=len(parsed.diagrams),
        diagrams_kept=len(diagram_results),
        diagrams_uploaded=diagrams_uploaded,
        diagrams_added=diagrams_added,
        diagrams_updated=diagrams_updated,
        diagrams_unchanged=diagrams_unchanged,
        diagrams_deleted=diagrams_deleted,
        vectors_upserted=len(to_upsert),
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
        "version_hash": c.metadata.get("version_hash", ""),
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
        "version_hash": d.version_hash,
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
