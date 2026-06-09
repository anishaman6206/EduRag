"""
Dense vector retriever.

Pipeline:
  1. Resolve which Pinecone namespaces to search, based on the
     Classification from the classifier (or from user pre-filters):
       - chapter fully resolved  → 1 namespace
       - subject + class         → all chapters of that pair
       - subject only            → all chapters of that subject
       - class only              → all chapters of that class
       - nothing                 → all 39 namespaces
  2. Embed the query once (with Redis-backed caching so repeat
     queries are free).
  3. Run parallel `query_namespace()` calls in one asyncio.gather.
     No BM25 / sparse search — the corpus is small enough that
     dense-only is faster end-to-end, and embedding caching makes
     the cost negligible.
  4. Fuse results across namespaces (no RRF — single-source dense).
     Sort by cosine score, drop below a relevance floor.
  5. Balance text vs diagram chunks (~75% text, ~25% diagrams).

Why this design (vs. earlier hybrid-with-BM25):
  - BM25 corpus build on first request is a 5-15s hit per namespace
  - With 22+ namespaces in scope, this adds up
  - Dense-only with a good embedding model beats BM25 for NCERT
    textbook questions (the vocabulary is well-defined)
  - Embedding cache eliminates the cost of repeat queries
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from config.constants import (
    NAMESPACE_MAP, RETRIEVAL_TOP_K, EMBEDDING_MODEL,
)
from services.pinecone_service import query_namespace
from services.openai_service import get_embedding

from rag.classifier import Classification
from rag.status import get_status_emitter, searching_message

logger = logging.getLogger(__name__)


# Hard cap on results — keeps latency predictable. Even with
# 39 namespaces hit in parallel, no more than this many chunks
# come back to the LLM.
MAX_RESULT_K = 12

# Cosine-similarity floor below which chunks are dropped.
# 0.5 is generous — NCERT chunks that don't reach it are
# usually about a different topic.
RELEVANCE_FLOOR = 0.5

# Max diagrams in the final result (the rest is text).
MAX_DIAGRAMS_IN_RESULT_RATIO = 0.25


# ─────────────────────────────────────────────────────────────────────────
# Data class
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class RetrievedChunk:
    id: str
    text: str
    score: float
    chapter_key: str
    class_level: str
    subject: str
    content_type: str
    parent_id: str | None
    page: int | None
    chunk_index: int | None
    diagram_url: str | None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_diagram(self) -> bool:
        return self.content_type == "diagram" or bool(self.diagram_url)


# ─────────────────────────────────────────────────────────────────────────
# Resolve which namespaces to search
# ─────────────────────────────────────────────────────────────────────────
def _resolve_namespaces(classification: Classification) -> list[tuple[str, str]]:
    """
    Return [(namespace, chapter_key), ...] to search. The order is
    stable across runs (sorted by chapter_key) so that per-namespace
    limits don't depend on dict insertion order.
    """
    if classification.is_fully_resolved:
        meta = classification.chapter_meta
        return [(meta["namespace"], classification.chapter_key)]

    if classification.subject and classification.class_level:
        return sorted(
            [
                (NAMESPACE_MAP[k]["namespace"], k)
                for k in NAMESPACE_MAP
                if NAMESPACE_MAP[k]["subject"] == classification.subject
                and NAMESPACE_MAP[k]["class_level"] == classification.class_level
            ],
            key=lambda x: x[1],
        )

    if classification.subject:
        return sorted(
            [
                (NAMESPACE_MAP[k]["namespace"], k)
                for k in NAMESPACE_MAP
                if NAMESPACE_MAP[k]["subject"] == classification.subject
            ],
            key=lambda x: x[1],
        )

    if classification.class_level:
        return sorted(
            [
                (NAMESPACE_MAP[k]["namespace"], k)
                for k in NAMESPACE_MAP
                if NAMESPACE_MAP[k]["class_level"] == classification.class_level
            ],
            key=lambda x: x[1],
        )

    # Last resort: search all 39 namespaces
    return sorted(
        [(v["namespace"], k) for k, v in NAMESPACE_MAP.items()],
        key=lambda x: x[1],
    )


# ─────────────────────────────────────────────────────────────────────────
# Embedding cache (Redis-backed)
#
# Why: a hot cache hit returns the vector in ~2ms vs ~600ms for
# the OpenAI round-trip. With gpt-4o-mini embeddings, this is
# also a real money saver on repeat queries (which is most of
# them — students ask follow-ups, and the same question gets
# asked many times in a class).
# ─────────────────────────────────────────────────────────────────────────
def _cache_key(text: str) -> str:
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"edurag:embed:{EMBEDDING_MODEL}:{digest}"


async def _get_embedding_cached(text: str) -> list[float]:
    """Embed with Redis cache. Falls back to a fresh embed on miss."""
    key = _cache_key(text)
    try:
        from services.redis_service import get_redis
        cached = await get_redis().get(key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        # Redis down (or just the in-memory fallback returning nothing) —
        # we silently proceed to a fresh embed.
        logger.debug("Embedding cache lookup failed: %s", e)

    vector = await get_embedding(text)

    try:
        from services.redis_service import get_redis
        await get_redis().setex(key, 86400, json.dumps(vector))  # 24h TTL
    except Exception as e:
        logger.debug("Embedding cache write failed: %s", e)

    return vector


# ─────────────────────────────────────────────────────────────────────────
# Match → chunk
# ─────────────────────────────────────────────────────────────────────────
_RESERVED_METADATA_KEYS = {
    "text", "chapter_key", "class_level", "subject",
    "content_type", "parent_id", "page", "chunk_index", "diagram_url",
}


def _match_to_chunk(m: dict[str, Any]) -> RetrievedChunk:
    md = m.get("metadata") or {}
    return RetrievedChunk(
        id=m["id"],
        text=md.get("text", ""),
        score=float(m["score"]),
        chapter_key=md.get("chapter_key", ""),
        class_level=md.get("class_level", ""),
        subject=md.get("subject", ""),
        content_type=md.get("content_type", "text"),
        parent_id=md.get("parent_id"),
        page=md.get("page"),
        chunk_index=md.get("chunk_index"),
        diagram_url=md.get("diagram_url"),
        extra={k: v for k, v in md.items() if k not in _RESERVED_METADATA_KEYS},
    )


# ─────────────────────────────────────────────────────────────────────────
# Main retriever
# ─────────────────────────────────────────────────────────────────────────
class HybridRetriever:
    """
    Stateless retriever. Safe to instantiate per request.
    Despite the name, this is now dense-only — see module docstring.
    """

    async def retrieve(
        self,
        query: str,
        classification: Classification,
        *,
        top_k: int = RETRIEVAL_TOP_K,
        filter: dict[str, Any] | None = None,
        query_vector: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        """
        Parallel Pinecone query across all resolved namespaces, with
        relevance floor + text/diagram balance.

        Args:
            query: The student's question.
            classification: Output of classify_query().
            top_k: Max chunks to return (capped at MAX_RESULT_K).
            filter: Optional Pinecone metadata filter.
            query_vector: Optional pre-computed query embedding. If
                provided, the retriever skips its own embed call.

        Returns:
            list of RetrievedChunk, ranked by cosine similarity.
        """
        # Best-effort status event emission (retrievers are not async
        # generators; the route handler also fires the status event).
        emitter = get_status_emitter()
        if emitter:
            try:
                await emitter(searching_message())
            except Exception:
                pass

        namespaces = _resolve_namespaces(classification)
        if not namespaces:
            return []

        # Embed once (or use the pre-computed vector).
        if query_vector is None:
            query_vector = await _get_embedding_cached(query)

        # Hard-cap the per-namespace top_k so we don't blow up when
        # 39 namespaces are in play. With 39 namespaces, each pulls
        # top_k / 39 chunks; we still get a clean fused list at the
        # end. With 1 namespace, we get top_k directly.
        per_ns_topk = max(3, min(top_k, MAX_RESULT_K) // max(1, len(namespaces)) + 2)

        # Run all dense queries in parallel.
        results = await asyncio.gather(
            *(
                query_namespace(
                    namespace=ns,
                    vector=query_vector,
                    top_k=per_ns_topk,
                    filter=filter,
                    include_metadata=True,
                )
                for ns, _ in namespaces
            ),
            return_exceptions=True,
        )

        # Flatten, convert to chunks, drop low-relevance + errors.
        all_chunks: list[RetrievedChunk] = []
        for ns, lst in zip(namespaces, results):
            if isinstance(lst, Exception):
                logger.warning("Dense query failed for %s: %s", ns[0], lst)
                continue
            for m in lst:
                chunk = _match_to_chunk(m)
                if chunk.score < RELEVANCE_FLOOR:
                    continue
                if not chunk.text:
                    continue
                all_chunks.append(chunk)

        # Sort by score descending.
        all_chunks.sort(key=lambda c: c.score, reverse=True)

        # Balance text vs diagrams: reserve ~25% slots for diagrams,
        # fill the rest with text chunks.
        max_diagrams = max(1, int(top_k * MAX_DIAGRAMS_IN_RESULT_RATIO))
        text_chunks = [c for c in all_chunks if not c.is_diagram]
        diagram_chunks = [c for c in all_chunks if c.is_diagram]

        result: list[RetrievedChunk] = []
        result.extend(text_chunks[: top_k - max_diagrams])
        result.extend(diagram_chunks[:max_diagrams])

        # Fill any remaining slots from the leftover pool.
        remaining = top_k - len(result)
        if remaining > 0:
            used = {c.id for c in result}
            for c in all_chunks:
                if remaining == 0:
                    break
                if c.id not in used:
                    result.append(c)
                    used.add(c.id)
                    remaining -= 1

        # Final hard cap.
        result = result[:MAX_RESULT_K]

        logger.info(
            "Retrieved %d chunks (text=%d, diagram=%d) across %d namespaces for query=%r",
            len(result),
            sum(1 for c in result if not c.is_diagram),
            sum(1 for c in result if c.is_diagram),
            len(namespaces),
            query[:80],
        )
        return result


# Module-level singleton (stateless, safe to share).
hybrid_retriever = HybridRetriever()
