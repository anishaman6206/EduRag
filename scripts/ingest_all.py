"""
ingest_all.py — bulk-ingest every chapter listed in NAMESPACE_MAP.

Walks pdfs/Data/ looking for matching PDF files. Skips the
*1ps* and *1an* files (preliminary section + answer key).

File naming convention (per docs/memory):
  8th Science/<bookcode>1NN.pdf  — bookcode = 'hecu'
  9th Science/<bookcode>1NN.pdf  — bookcode = 'iesc'
  10th Science/<bookcode>1NN.pdf — bookcode = 'jesc'

Usage:
    python scripts/ingest_all.py
    python scripts/ingest_all.py --upload-diagrams
    python scripts/ingest_all.py --class-filter 8 9
    python scripts/ingest_all.py --subject-filter physics
    python scripts/ingest_all.py --dry-run

Expected time for the full 22-chapter ingest:
  - Without --upload-diagrams:  ~10-15 minutes
    (each chapter takes 30-90s; 22 chapters)
  - With --upload-diagrams:     ~15-25 minutes
    (adds ~5-10s per chapter for 27 diagram uploads)

Total cost (OpenAI + Pinecone):
  - Embeddings: 22 chapters × ~60 chunks × $0.00002 = ~$0.03
  - LLM (none — only embeddings are used at ingest time)
  - Pinecone: serverless, free tier covers 22 chapters
  - Supabase storage (if --upload-diagrams): 22 × 27 × avg-50KB = ~30MB
"""

from __future__ import annotations
import argparse
import asyncio
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from config.constants import NAMESPACE_MAP
from ingestion.pipeline import run_ingestion


# ─────────────────────────────────────────────────────────────────────────
# Filename → chapter_key resolver
# ─────────────────────────────────────────────────────────────────────────
BOOKCODES = {
    "8":  "hecu",   # Class 8 Science
    "9":  "iesc",   # Class 9 Science
    "10": "jesc",   # Class 10 Science
}

# Files matching these patterns are skipped
SKIP_PATTERNS = ["1ps", "1an", "200ans"]


def resolve_pdf_path(pdf_dir: Path, chapter_key: str) -> Path | None:
    """
    Look for a PDF file matching this chapter_key. Returns None
    if not found. The file pattern is {bookcode}1{NN}.pdf where
    bookcode is per-class and NN is the chapter number zero-padded.

    Example: physics_8_ch4 → /pdfs/Data/8th Science/hecu104.pdf
    """
    meta = NAMESPACE_MAP[chapter_key]
    class_level = meta["class_level"]
    chapter_num = meta["chapter_number"]
    bookcode = BOOKCODES.get(class_level)
    if not bookcode:
        return None

    book_dir = pdf_dir / f"{class_level}th Science"
    if not book_dir.exists():
        return None

    # Zero-pad the chapter number to 2 digits
    filename = f"{bookcode}1{chapter_num:02d}.pdf"
    candidate = book_dir / filename
    return candidate if candidate.exists() else None


# ─────────────────────────────────────────────────────────────────────────
# Args
# ─────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bulk-ingest every NCERT chapter in NAMESPACE_MAP.")
    p.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path("pdfs/Data"),
        help="Root dir containing the {N}th Science/ subfolders (default: pdfs/Data)",
    )
    p.add_argument(
        "--upload-diagrams",
        action="store_true",
        help="Upload extracted diagram images to Supabase Storage.",
    )
    p.add_argument(
        "--class-filter",
        nargs="+",
        choices=["7", "8", "9", "10"],
        help="Only ingest these classes (default: all)",
    )
    p.add_argument(
        "--subject-filter",
        nargs="+",
        choices=["math", "physics", "chemistry"],
        help="Only ingest these subjects (default: all)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List which PDFs would be ingested, but don't actually ingest.",
    )
    return p.parse_args()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class ChapterResult:
    chapter_key: str
    pdf_path: Path
    success: bool
    duration: float
    error: str | None = None
    summary: dict | None = None


async def ingest_one(
    chapter_key: str,
    pdf_path: Path,
    upload_diagrams: bool,
) -> ChapterResult:
    t0 = time.monotonic()
    try:
        summary = await run_ingestion(
            pdf_path=str(pdf_path),
            chapter_key=chapter_key,
            upload_diagrams_to_storage=upload_diagrams,
        )
        return ChapterResult(
            chapter_key=chapter_key,
            pdf_path=pdf_path,
            success=True,
            duration=time.monotonic() - t0,
            summary=summary.__dict__ if hasattr(summary, "__dict__") else None,
        )
    except Exception as e:
        return ChapterResult(
            chapter_key=chapter_key,
            pdf_path=pdf_path,
            success=False,
            duration=time.monotonic() - t0,
            error=str(e),
        )


async def main() -> int:
    args = parse_args()
    setup_logging()

    class_filter = set(args.class_filter or [])
    subject_filter = set(args.subject_filter or [])

    # Plan
    plan: list[tuple[str, Path]] = []
    missing: list[str] = []
    for chapter_key, meta in NAMESPACE_MAP.items():
        if class_filter and meta["class_level"] not in class_filter:
            continue
        if subject_filter and meta["subject"] not in subject_filter:
            continue
        pdf_path = resolve_pdf_path(args.pdf_dir, chapter_key)
        if pdf_path is None:
            missing.append(chapter_key)
            continue
        plan.append((chapter_key, pdf_path))

    print(f"Plan: {len(plan)} chapters to ingest, {len(missing)} missing PDFs")
    for ck, p in plan:
        print(f"  ✓ {ck:18s}  →  {p}")
    for ck in missing:
        print(f"  ✗ {ck:18s}  (no PDF found at expected path)")

    if args.dry_run:
        print("\n[DRY RUN] Exiting without ingesting.")
        return 0

    if not plan:
        print("Nothing to ingest.")
        return 0

    # Ingest sequentially. Could parallelize but the OpenAI rate
    # limits would make us slow down anyway. Sequential also makes
    # logs easier to read.
    results: list[ChapterResult] = []
    for i, (ck, pdf_path) in enumerate(plan, 1):
        print(f"\n[{i}/{len(plan)}] Ingesting {ck} from {pdf_path}")
        result = await ingest_one(ck, pdf_path, args.upload_diagrams)
        results.append(result)
        if result.success:
            print(f"  ✓ Done in {result.duration:.1f}s")
        else:
            print(f"  ✗ Failed in {result.duration:.1f}s: {result.error}")

    # Final summary
    print("\n" + "=" * 60)
    print("BULK INGEST COMPLETE")
    print("=" * 60)
    succeeded = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    total_duration = sum(r.duration for r in results)
    print(f"  Succeeded: {len(succeeded)} / {len(results)}")
    print(f"  Failed:    {len(failed)}")
    print(f"  Total time: {total_duration / 60:.1f} min ({total_duration:.0f}s)")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  - {r.chapter_key}: {r.error}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
