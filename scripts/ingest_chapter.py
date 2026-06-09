"""
ingest_chapter.py — CLI: ingest a single chapter PDF.

Usage:
    python scripts/ingest_chapter.py \\
        --chapter-key physics_9_ch4 \\
        --pdf ./pdfs/Data/9th Science/iesc104.pdf

    # Re-ingest and upload diagram images to Supabase Storage:
    python scripts/ingest_chapter.py \\
        --chapter-key physics_9_ch4 \\
        --pdf ./pdfs/Data/9th Science/iesc104.pdf \\
        --upload-diagrams

    # Dry-run (parse + chunk, don't upsert anything)
    python scripts/ingest_chapter.py \\
        --chapter-key physics_9_ch4 \\
        --pdf ./pdfs/Data/9th Science/iesc104.pdf \\
        --dry-run
"""

from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Make `backend` importable when running from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from config.constants import NAMESPACE_MAP
from ingestion.pipeline import run_ingestion


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest a single NCERT chapter PDF into EduRag.")
    p.add_argument(
        "--chapter-key",
        required=True,
        help="The chapter_key from NAMESPACE_MAP, e.g. 'physics_8_ch4'",
    )
    p.add_argument(
        "--pdf",
        required=True,
        type=Path,
        help="Path to the chapter PDF file",
    )
    p.add_argument(
        "--upload-diagrams",
        action="store_true",
        help="Upload extracted diagram images to Supabase Storage (requires the bucket to exist).",
    )
    p.add_argument(
        "--no-rollback",
        action="store_true",
        help="Skip namespace rollback on failure (default: rollback is enabled).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + chunk + embed but don't upsert. Use for sanity-checking.",
    )
    return p.parse_args()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


async def main() -> int:
    args = parse_args()
    setup_logging()

    if args.chapter_key not in NAMESPACE_MAP:
        print(f"ERROR: Unknown chapter_key '{args.chapter_key}'", file=sys.stderr)
        print(f"Valid keys: {sorted(NAMESPACE_MAP.keys())}", file=sys.stderr)
        return 1

    if not args.pdf.exists():
        print(f"ERROR: PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    meta = NAMESPACE_MAP[args.chapter_key]
    print(f"Ingesting chapter: {args.chapter_key}")
    print(f"  Display name : {meta['display_name']}")
    print(f"  Subject/Class: {meta['subject']} / {meta['class_level']}")
    print(f"  PDF path     : {args.pdf}")
    print(f"  Upload images: {args.upload_diagrams}")
    print(f"  Dry run      : {args.dry_run}")
    print()

    if args.dry_run:
        # Parse + chunk only — no embeddings, no upsert
        from ingestion.pdf_parser import parse_pdf
        from ingestion.chunker import create_chunks
        from config.constants import get_chapter_meta

        meta = get_chapter_meta(args.chapter_key)
        metadata = {
            "chapter_key": args.chapter_key,
            "class_level": meta["class_level"],
            "subject": meta["subject"],
            "namespace": meta["namespace"],
            "display_name": meta["display_name"],
        }
        doc = parse_pdf(str(args.pdf), metadata=metadata)
        print(f"[DRY RUN] {len(doc.pages)} pages, {len(doc.diagrams)} diagram candidates, {len(doc.raw_text)} chars")
        parents, children = await create_chunks(doc, metadata)
        print(f"[DRY RUN] {len(parents)} parents, {len(children)} children (no embeddings computed)")
        return 0

    summary = await run_ingestion(
        pdf_path=str(args.pdf),
        chapter_key=args.chapter_key,
        upload_diagrams_to_storage=args.upload_diagrams,
        rollback_on_failure=not args.no_rollback,
    )

    print()
    print("=" * 60)
    print("INGESTION COMPLETE")
    print("=" * 60)
    print(f"  Chapter        : {summary.chapter_key}")
    print(f"  Namespace      : {summary.namespace}")
    print(f"  Duration       : {summary.duration_seconds}s")
    print(f"  Parents        : {summary.parents_created} created")
    print(f"  Children       : +{summary.children_added} added, ~{summary.children_updated} updated, ={summary.children_unchanged} unchanged, -{summary.children_deleted} deleted")
    print(f"  Diagrams       : {summary.diagrams_found} found, {summary.diagrams_kept} kept, {summary.diagrams_uploaded} uploaded")
    print(f"  Vectors        : {summary.vectors_upserted} upserted")
    if summary.errors:
        print(f"  Errors         : {len(summary.errors)}")
        for e in summary.errors:
            print(f"    - {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
