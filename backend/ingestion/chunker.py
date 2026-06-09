"""
Semantic chunker with parent/child structure.

Pipeline:
  1. Split parsed pages into sentences.
  2. Compute cosine similarity between consecutive sentence embeddings.
  3. Cut a new parent chunk wherever similarity drops below
     SEMANTIC_CHUNK_SIM_THRESHOLD (0.5). This gives ~1200-token
     semantic blocks that hold together as a concept.
  4. Split each parent into ~300-token children, with rules:
     - Never split mid-formula (don't cut inside $...$ or $$...$$).
     - Never split mid-sentence.
     - Tag content_type per child: text | formula | definition | example.

Why parent/child:
  - A 300-token child is small enough to embed precisely and to match
    focused questions, but lacks surrounding context. A 1200-token
    parent provides that context to the LLM at generation time.
  - When a child matches, the retriever returns it, the generator
    swaps in the parent for the LLM context. Best of both worlds.

The chunker doesn't embed text itself — it returns chunk records with
positions, and the embedder (or the pipeline) computes embeddings
in a single batched call (cheaper than one-by-one).
"""

from __future__ import annotations
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

import tiktoken

from config.constants import (
    PARENT_CHUNK_TARGET_TOKENS,
    CHILD_CHUNK_TARGET_TOKENS,
    SEMANTIC_CHUNK_SIM_THRESHOLD,
    EMBEDDING_BATCH_SIZE,
)
from services.openai_service import get_embeddings

from ingestion.pdf_parser import ParsedDocument

logger = logging.getLogger(__name__)


# Use cl100k_base — the tokenizer gpt-4 / text-embedding-3-small use.
# Loading once at module import (it's bundled with tiktoken, no network).
_tokenizer = tiktoken.get_encoding("cl100k_base")


# ─────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class ParentChunk:
    """A ~1200-token block of coherent textbook content."""
    id: str                           # p_<hash8>  — used as Supabase row key
    chapter_key: str
    content: str
    token_count: int
    content_type: str                 # most common child type, or "text"
    page_start: int | None
    page_end: int | None
    metadata: dict = field(default_factory=dict)


@dataclass
class ChildChunk:
    """A ~300-token slice of a parent. Embedded and stored in Pinecone."""
    id: str                           # f"{chapter_key}_{idx}_{parent_hash[:8]}"
    parent_id: str
    chapter_key: str
    class_level: str
    subject: str
    content: str                      # the text we'll embed
    text: str                         # alias of content (Pinecone metadata uses 'text')
    token_count: int
    content_type: str                 # "text" | "formula" | "definition" | "example"
    chunk_index: int                  # position within the parent
    page: int | None
    metadata: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
# Sentence splitting + formula-aware re-joining
# ─────────────────────────────────────────────────────────────────────────
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\$])")
# Don't split on periods that are inside numbers like "3.14" or "Fig. 2"


def _split_sentences(text: str) -> list[str]:
    """Naive sentence splitter that's good enough for NCERT prose."""
    text = text.strip()
    if not text:
        return []
    # Split on the boundary but preserve the trailing period on each piece
    parts = _SENTENCE_END.split(text)
    return [p.strip() for p in parts if p.strip()]


def _detect_content_type(text: str) -> str:
    """
    Classify a chunk's content. Heuristics:
      - has $$..$$ or $..$ with operators  → "formula"
      - starts with "Example" / "Q." / "Solution"  → "example"
      - starts with verb "is" / "are" / "refers to"  → "definition"
      - default → "text"
    """
    has_block = "$$" in text
    has_inline = bool(re.search(r"\$[^$\n]+\$", text))
    has_operators = bool(re.search(r"[=+\-*/]\s*[A-Za-z(]|\\frac|\\sum|\\int", text))

    if (has_block or has_inline) and has_operators:
        return "formula"

    stripped = text.lstrip()
    low = stripped.lower()
    if low.startswith(("example", "e.g.", "q.", "solution:", "worked out", "let us solve", "let’s solve")):
        return "example"
    if low.startswith(("definition:", "is defined as", "refers to", "means ")):
        return "definition"

    return "text"


def _is_formula_block(text: str) -> bool:
    """True if the text contains any LaTeX formula (block or inline)."""
    if "$$" in text:
        return True
    if re.search(r"\$[^$\n]+\$", text):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# Step 1: sentence-level semantic segmentation → parent candidates
# ─────────────────────────────────────────────────────────────────────────
async def _semantic_parents(
    sentences: list[str],
    page_for_sentence: list[int],
    chapter_key: str,
) -> list[ParentChunk]:
    """
    Group sentences into ~PARENT_CHUNK_TARGET_TOKENS-token blocks,
    cutting where consecutive-sentence cosine similarity drops.
    """
    if not sentences:
        return []

    # Embed every sentence (batch via the existing helper)
    logger.info("Embedding %d sentences for semantic chunking", len(sentences))
    embeddings: list[list[float]] = await get_embeddings(sentences)

    # Cosine similarity between consecutive sentence vectors
    def _cos(a: list[float], b: list[float]) -> float:
        # numpy-free so we don't add a hard dep just for this
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    # Walk sentences, accumulate into a current parent until either
    # we hit the token budget OR a low-similarity boundary.
    parents: list[ParentChunk] = []
    cur_text: list[str] = []
    cur_tokens = 0
    cur_pages: list[int] = []

    for i, sent in enumerate(sentences):
        sent_tokens = len(_tokenizer.encode(sent))

        # Decide if we should cut BEFORE adding this sentence
        should_cut = False
        if cur_text and cur_tokens + sent_tokens > PARENT_CHUNK_TARGET_TOKENS:
            should_cut = True
        elif (
            i > 0
            and cur_tokens > 200                          # not too early
            and _cos(embeddings[i - 1], embeddings[i]) < SEMANTIC_CHUNK_SIM_THRESHOLD
        ):
            should_cut = True

        if should_cut and cur_text:
            parents.append(_make_parent(
                chapter_key=chapter_key,
                text=" ".join(cur_text),
                page_start=cur_pages[0] if cur_pages else None,
                page_end=cur_pages[-1] if cur_pages else None,
            ))
            cur_text = []
            cur_tokens = 0
            cur_pages = []

        cur_text.append(sent)
        cur_tokens += sent_tokens
        cur_pages.append(page_for_sentence[i])

    # Flush the last in-progress parent
    if cur_text:
        parents.append(_make_parent(
            chapter_key=chapter_key,
            text=" ".join(cur_text),
            page_start=cur_pages[0] if cur_pages else None,
            page_end=cur_pages[-1] if cur_pages else None,
        ))

    logger.info("Created %d parent chunks from %d sentences", len(parents), len(sentences))
    return parents


def _make_parent(*, chapter_key: str, text: str, page_start: int | None, page_end: int | None) -> ParentChunk:
    """Hash the content so the parent_id is deterministic for re-ingest."""
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return ParentChunk(
        id=f"p_{h}",
        chapter_key=chapter_key,
        content=text,
        token_count=len(_tokenizer.encode(text)),
        content_type=_detect_content_type(text),
        page_start=page_start,
        page_end=page_end,
        metadata={"content_hash": h},
    )


# ─────────────────────────────────────────────────────────────────────────
# Step 2: split each parent into ~CHILD_CHUNK_TARGET_TOKENS children,
# never cutting inside a formula block.
# ─────────────────────────────────────────────────────────────────────────
_FORMULA_BLOCK = re.compile(r"\$\$[^$]+?\$\$", re.DOTALL)
_INLINE_FORMULA = re.compile(r"\$[^$\n]+?\$")


def _split_children(parent: ParentChunk) -> list[ChildChunk]:
    """
    Split a parent into children, with formula-aware boundaries.
    We do a simple word-walk: accumulate words, but if the next
    word would push us past the token budget AND we have a
    formula-safe boundary (a period, newline, or closing $$),
    cut there. Never cut inside a formula.
    """
    text = parent.content
    if not text.strip():
        return []

    # First: identify formula spans (positions of $$..$$ and $..$)
    # so we never cut inside one. We treat the whole span as atomic.
    formula_spans: list[tuple[int, int]] = []
    for m in _FORMULA_BLOCK.finditer(text):
        formula_spans.append((m.start(), m.end()))
    for m in _INLINE_FORMULA.finditer(text):
        # avoid double-counting if the inline is inside a block
        if any(s <= m.start() < e for s, e in formula_spans):
            continue
        formula_spans.append((m.start(), m.end()))

    def in_formula(pos: int) -> bool:
        return any(s <= pos < e for s, e in formula_spans)

    # Tokenize once and walk through token positions
    tokens = _tokenizer.encode(text)
    # We don't have a clean offset-by-token mapping from tiktoken,
    # so we work on the text level: find safe cut points (sentence ends,
    # newlines, closing $$), then compute token counts of substrings.

    # Build a list of "safe cut positions" — characters where it's OK to cut
    safe_cuts: list[int] = [0]
    for i, ch in enumerate(text):
        if in_formula(i):
            continue
        if ch in ".!?\n" and i + 1 < len(text):
            safe_cuts.append(i + 1)
    safe_cuts.append(len(text))

    children: list[ChildChunk] = []
    cursor = 0
    idx = 0
    while cursor < len(text):
        # Find the longest safe substring starting at cursor whose
        # token count is <= CHILD_CHUNK_TARGET_TOKENS.
        # Walk safe_cuts from the highest down to the lowest.
        target_tokens = CHILD_CHUNK_TARGET_TOKENS
        best_end = cursor
        for end in safe_cuts:
            if end <= cursor:
                continue
            if end > len(text):
                end = len(text)
            piece = text[cursor:end]
            tcount = len(_tokenizer.encode(piece))
            if tcount > target_tokens:
                # Going past budget — stop, use the previous best
                break
            best_end = end
        # If best_end didn't move (a single sentence is bigger than
        # the budget), take the whole thing anyway — we don't want
        # to lose content. The 300-token target is a soft cap.
        if best_end == cursor:
            # Force cut at next safe cut
            for end in safe_cuts:
                if end > cursor:
                    best_end = end
                    break
            if best_end == cursor:
                best_end = len(text)  # last resort

        piece = text[cursor:best_end].strip()
        if piece:
            children.append(ChildChunk(
                id=f"{parent.chapter_key}_{idx}_{parent.metadata['content_hash']}",
                parent_id=parent.id,
                chapter_key=parent.chapter_key,
                class_level=parent.metadata.get("class_level", ""),
                subject=parent.metadata.get("subject", ""),
                content=piece,
                text=piece,
                token_count=len(_tokenizer.encode(piece)),
                content_type=_detect_content_type(piece),
                chunk_index=idx,
                page=parent.page_start,  # rough — first page the parent spans
                metadata={
                    "content_hash": parent.metadata["content_hash"],
                    "page_end": parent.page_end,
                },
            ))
            idx += 1
        cursor = best_end

    return children


# ─────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────
async def create_chunks(
    parsed: ParsedDocument,
    metadata: dict,
) -> tuple[list[ParentChunk], list[ChildChunk]]:
    """
    Turn a ParsedDocument into (parents, children).

    Args:
        parsed: Output of pdf_parser.parse_pdf().
        metadata: Must include chapter_key, class_level, subject
                  (looked up from NAMESPACE_MAP by the pipeline).

    Returns:
        (parents, children) — parents go to Supabase, children get
        embedded and upserted to Pinecone.
    """
    chapter_key = metadata.get("chapter_key")
    if not chapter_key:
        raise ValueError("metadata['chapter_key'] is required")

    # Flatten pages into a stream of (sentence, page_number) so we
    # can preserve page provenance through chunking.
    sentences: list[str] = []
    pages: list[int] = []
    for page in parsed.pages:
        for sent in _split_sentences(page.text):
            sentences.append(sent)
            pages.append(page.page_number)

    logger.info("Splitting %d sentences from %d pages", len(sentences), len(parsed.pages))

    # Step 1: parents (semantic)
    parents = await _semantic_parents(sentences, pages, chapter_key)

    # Attach class/subject onto each parent so children inherit it
    for p in parents:
        p.metadata.update({
            "class_level": metadata.get("class_level", ""),
            "subject": metadata.get("subject", ""),
        })

    # Step 2: children (formula-safe splits)
    all_children: list[ChildChunk] = []
    for p in parents:
        all_children.extend(_split_children(p))

    logger.info(
        "create_chunks(%s): %d parents → %d children",
        chapter_key, len(parents), len(all_children),
    )
    return parents, all_children
