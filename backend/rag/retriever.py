"""
Hybrid retriever.

Pipeline:
  1. Resolve the search target from the Classification:
     - If chapter_key is trusted → search that one Pinecone namespace.
     - If only subject+class are known → search every chapter of that
       pair, fused across namespaces.
     - If nothing is known → search a "broad" set of all 55 namespaces.
  2. Dense search via Pinecone vector query on each resolved namespace.
  3. Sparse search via BM25 over an in-memory corpus of the same
     chunks. The corpus is built lazily on first use and cached
     per-namespace for the lifetime of the process. (55 chapters is
     small enough that the in-memory cache is fine; swap to a
     persistent sparse index if chapters grow large.)
  4. Fuse the two ranked lists with Reciprocal Rank Fusion
     (RRF_DENSE_WEIGHT * dense_rank + RRF_SPARSE_WEIGHT * sparse_rank,
     using 1/(k + rank) scoring).
  5. Return the top RETRIEVAL_TOP_K fused chunks, with metadata
     (parent_id, page, content_type, etc.) intact for the reranker
     and the SSE `sources` event.

The retriever returns a list of RetrievedChunk. The caller (the
generator) splits this into text chunks and diagram chunks and uses
them differently.
"""

from __future__ import annotations
import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import Any

from rank_bm25 import BM25Okapi

from config.constants import (
    NAMESPACE_MAP, RETRIEVAL_TOP_K, RRF_DENSE_WEIGHT, RRF_SPARSE_WEIGHT,
)
from config.settings import get_settings
from services.pinecone_service import query_namespace
from services.openai_service import get_embedding

from rag.classifier import Classification

logger = logging.getLogger(__name__)


# RRF constant — higher k reduces the impact of rank-1 dominance.
_RRF_K = 60


# ─────────────────────────────────────────────────────────────────────────
# Data class — what flows out of the retriever
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class RetrievedChunk:
    """One retrieved chunk, with all metadata needed by the generator and SSE."""
    id: str
    text: str
    score: float                  # final fused RRF score
    dense_score: float | None     # raw cosine similarity, if available
    sparse_score: float | None    # raw BM25 score, if available
    chapter_key: str
    class_level: str
    subject: str
    content_type: str             # "text" | "formula" | "definition" | "example" | "diagram"
    parent_id: str | None
    page: int | None
    chunk_index: int | None
    diagram_url: str | None       # populated only for diagram chunks
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_diagram(self) -> bool:
        return self.content_type == "diagram" or bool(self.diagram_url)


# ─────────────────────────────────────────────────────────────────────────
# BM25 corpus cache — one BM25 index per Pinecone namespace.
# Built lazily on first use by fetching all child-chunk IDs and
# their `text` metadata from Pinecone. (Vector values aren't needed
# for BM25 — we only use the text.)
# ─────────────────────────────────────────────────────────────────────────
class _SparseIndex:
    """Lazy per-namespace BM25 index."""

    def __init__(self, namespace: str):
        self.namespace = namespace
        self._bm25: BM25Okapi | None = None
        self._chunk_ids: list[str] = []
        self._texts: list[str] = []
        self._meta: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return self._bm25 is not None

    async def build(self) -> None:
        """
        Enumerate every vector in the namespace and index its text.
        Two-step process because pinecone-py's list() yields batches
        of vector IDs only, and we need metadata:
          1. list()  — paginated generator of batches of IDs
          2. fetch() — bulk fetch full vectors (with metadata) for each batch
        """
        from services.pinecone_service import get_index

        index = get_index()
        try:
            all_ids: list[str] = []
            # list() returns a generator yielding lists of vector ID strings.
            # We accumulate them, then fetch in batches of 100.
            for id_batch in index.list(prefix="", namespace=self.namespace):
                all_ids.extend(id_batch)

            if not all_ids:
                logger.info("BM25: namespace %s has no chunks", self.namespace)
                return

            ids, texts, meta = [], [], []
            FETCH_BATCH = 100
            for i in range(0, len(all_ids), FETCH_BATCH):
                batch_ids = all_ids[i:i + FETCH_BATCH]
                response = index.fetch(ids=batch_ids, namespace=self.namespace)
                # response.vectors is a dict {id: Vector}
                for vec_id, vec in (response.vectors or {}).items():
                    md = dict(vec.metadata or {})
                    text = md.get("text", "")
                    if not text:
                        continue
                    ids.append(vec_id)
                    texts.append(text)
                    meta.append(md)
        except Exception as e:
            logger.warning("BM25 build for %s failed: %s", self.namespace, e)
            return

        if not texts:
            # Mark as built (with an empty index) so ensure_built() doesn't
            # retry forever against a namespace that simply has no data.
            self._bm25 = None
            logger.info("BM25: namespace %s has no chunks", self.namespace)
            return

        tokenized = [t.lower().split() for t in texts]
        self._bm25 = BM25Okapi(tokenized)
        self._chunk_ids = ids
        self._texts = texts
        self._meta = meta
        logger.info("BM25: indexed %d chunks in %s", len(texts), self.namespace)

    async def ensure_built(self) -> None:
        if self._bm25 is None:
            async with self._lock:
                if self._bm25 is None:
                    await self.build()

    async def search(self, query: str, top_k: int) -> list[tuple[str, str, dict, float]]:
        """
        Returns [(chunk_id, text, metadata, bm25_score), ...] for the
        top_k highest-scoring chunks.
        """
        await self.ensure_built()
        if self._bm25 is None or not self._texts:
            return []
        tokenized_query = query.lower().split()
        scores = self._bm25.get_scores(tokenized_query)
        # argsort descending, take top_k
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            (self._chunk_ids[i], self._texts[i], self._meta[i], float(scores[i]))
            for i, _ in ranked
            if scores[i] > 0
        ]


# Process-level cache of BM25 indexes, keyed by namespace
_sparse_cache: dict[str, _SparseIndex] = {}


def _get_sparse(namespace: str) -> _SparseIndex:
    if namespace not in _sparse_cache:
        _sparse_cache[namespace] = _SparseIndex(namespace)
    return _sparse_cache[namespace]


# ─────────────────────────────────────────────────────────────────────────
# Resolve which namespaces to search
# ─────────────────────────────────────────────────────────────────────────
def _resolve_namespaces(classification: Classification) -> list[tuple[str, str]]:
    """
    Return [(namespace, chapter_key), ...] to search. Ordering matters
    when no specific chapter is known — we use the same chapter order
    as NAMESPACE_MAP for determinism.
    """
    if classification.is_fully_resolved:
        meta = classification.chapter_meta
        return [(meta["namespace"], classification.chapter_key)]

    if classification.subject and classification.class_level:
        return [
            (NAMESPACE_MAP[k]["namespace"], k)
            for k in NAMESPACE_MAP
            if NAMESPACE_MAP[k]["subject"] == classification.subject
            and NAMESPACE_MAP[k]["class_level"] == classification.class_level
        ]

    # Last resort: search everything
    return [(v["namespace"], k) for k, v in NAMESPACE_MAP.items()]


# ─────────────────────────────────────────────────────────────────────────
# Convert Pinecone match + metadata to RetrievedChunk
# ─────────────────────────────────────────────────────────────────────────
def _match_to_chunk(
    chunk_id: str,
    text: str,
    score: float,
    metadata: dict[str, Any],
    *,
    dense_score: float | None = None,
    sparse_score: float | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        text=text,
        score=score,
        dense_score=dense_score,
        sparse_score=sparse_score,
        chapter_key=metadata.get("chapter_key", ""),
        class_level=metadata.get("class_level", ""),
        subject=metadata.get("subject", ""),
        content_type=metadata.get("content_type", "text"),
        parent_id=metadata.get("parent_id"),
        page=metadata.get("page"),
        chunk_index=metadata.get("chunk_index"),
        diagram_url=metadata.get("diagram_url"),
        extra={k: v for k, v in metadata.items()
               if k not in {"text", "chapter_key", "class_level", "subject",
                            "content_type", "parent_id", "page", "chunk_index",
                            "diagram_url"}},
    )


# ─────────────────────────────────────────────────────────────────────────
# Reciprocal Rank Fusion
# ─────────────────────────────────────────────────────────────────────────
def _rrf_fuse(
    dense_results: dict[str, tuple[RetrievedChunk, int]],   # id -> (chunk, dense_rank)
    sparse_results: dict[str, tuple[RetrievedChunk, int]],  # id -> (chunk, sparse_rank)
) -> list[RetrievedChunk]:
    """
    Combine two ranked lists into one via RRF.
    Score = alpha / (k + dense_rank) + (1-alpha) / (k + sparse_rank)
    A chunk present in only one list still gets a score from that list.
    """
    alpha = RRF_DENSE_WEIGHT
    beta = RRF_SPARSE_WEIGHT
    all_ids = set(dense_results) | set(sparse_results)
    scored: list[RetrievedChunk] = []

    for cid in all_ids:
        d = dense_results.get(cid)
        s = sparse_results.get(cid)
        # Use the dense chunk as the base if present, else sparse
        chunk = (d or s)[0]

        rrf = 0.0
        if d is not None:
            rrf += alpha / (_RRF_K + d[1])
        if s is not None:
            rrf += beta / (_RRF_K + s[1])

        # Attach the new fused score
        chunk = RetrievedChunk(
            id=chunk.id, text=chunk.text, score=rrf,
            dense_score=chunk.dense_score, sparse_score=chunk.sparse_score,
            chapter_key=chunk.chapter_key, class_level=chunk.class_level,
            subject=chunk.subject, content_type=chunk.content_type,
            parent_id=chunk.parent_id, page=chunk.page,
            chunk_index=chunk.chunk_index, diagram_url=chunk.diagram_url,
            extra=chunk.extra,
        )
        scored.append(chunk)

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


# ─────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────
class HybridRetriever:
    """Stateless retriever. Safe to instantiate per request."""

    async def retrieve(
        self,
        query: str,
        classification: Classification,
        *,
        top_k: int = RETRIEVAL_TOP_K,
        filter: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """
        Hybrid (dense + sparse) retrieval with RRF fusion.

        Args:
            query: The student's question.
            classification: Output of classify_query().
            top_k: Max chunks to return. Pulls 2x from each retriever
                   before fusion so fusion can find a good top_k.
            filter: Optional Pinecone metadata filter
                    (e.g. {"content_type": {"$in": ["text", "formula"]}}).

        Returns:
            list of RetrievedChunk, fused and ranked, length <= top_k.
        """
        namespaces = _resolve_namespaces(classification)
        if not namespaces:
            return []

        # 1. Embed the query once for the dense side
        query_vector = await get_embedding(query)

        # 2. Run dense + sparse in parallel across all resolved namespaces
        per_ns_topk = max(5, math.ceil(top_k / len(namespaces)) + 2)

        dense_tasks = [
            self._dense_one(ns, chapter_key, query_vector, per_ns_topk, filter)
            for ns, chapter_key in namespaces
        ]
        sparse_tasks = [
            self._sparse_one(ns, chapter_key, query, per_ns_topk)
            for ns, chapter_key in namespaces
        ]
        dense_lists, sparse_lists = await asyncio.gather(
            asyncio.gather(*dense_tasks, return_exceptions=True),
            asyncio.gather(*sparse_tasks, return_exceptions=True),
        )

        # 3. Flatten results across namespaces
        all_dense: dict[str, tuple[RetrievedChunk, int]] = {}
        for lst in dense_lists:
            if isinstance(lst, Exception):
                logger.warning("Dense namespace failed: %s", lst)
                continue
            for rank, chunk in enumerate(lst, start=1):
                # If a chunk appears in multiple namespaces (shouldn't
                # happen — namespaces are disjoint by chapter — but be
                # safe), keep the one with the lower rank.
                if chunk.id not in all_dense or all_dense[chunk.id][1] > rank:
                    all_dense[chunk.id] = (chunk, rank)

        all_sparse: dict[str, tuple[RetrievedChunk, int]] = {}
        for lst in sparse_lists:
            if isinstance(lst, Exception):
                logger.warning("Sparse namespace failed: %s", lst)
                continue
            for rank, chunk in enumerate(lst, start=1):
                if chunk.id not in all_sparse or all_sparse[chunk.id][1] > rank:
                    all_sparse[chunk.id] = (chunk, rank)

        # 4. Fuse with RRF
        fused = _rrf_fuse(all_dense, all_sparse)

        # 5. Balance text vs diagram chunks.
        # Diagram chunks dominate the index (we keep all of them per
        # chapter), so a pure top-K cut returns diagrams only. We
        # reserve a slot for diagrams and fill the rest with text/
        # formula/definition/example chunks.
        MAX_DIAGRAMS_IN_RESULT = max(1, top_k // 4)   # ~25% of results are diagrams

        text_chunks = [c for c in fused if not c.is_diagram]
        diagram_chunks = [c for c in fused if c.is_diagram]

        result: list[RetrievedChunk] = []
        result.extend(text_chunks[: top_k - MAX_DIAGRAMS_IN_RESULT])
        result.extend(diagram_chunks[:MAX_DIAGRAMS_IN_RESULT])

        # If we still have room, fill from whichever pool has more
        remaining_room = top_k - len(result)
        if remaining_room > 0:
            used_ids = {c.id for c in result}
            for c in fused:
                if remaining_room == 0:
                    break
                if c.id not in used_ids:
                    result.append(c)
                    used_ids.add(c.id)
                    remaining_room -= 1

        logger.info(
            "Retrieved %d chunks (text=%d, diagram=%d; dense=%d, sparse=%d, namespaces=%d) for query=%r",
            len(result),
            sum(1 for c in result if not c.is_diagram),
            sum(1 for c in result if c.is_diagram),
            len(all_dense), len(all_sparse), len(namespaces),
            query[:80],
        )
        return result

    @staticmethod
    async def _dense_one(
        namespace: str,
        chapter_key: str,
        query_vector: list[float],
        top_k: int,
        filter: dict[str, Any] | None,
    ) -> list[RetrievedChunk]:
        try:
            matches = await query_namespace(
                namespace=namespace,
                vector=query_vector,
                top_k=top_k,
                filter=filter,
                include_metadata=True,
            )
        except Exception as e:
            logger.warning("Dense query failed for %s: %s", namespace, e)
            return []

        return [
            _match_to_chunk(
                chunk_id=m["id"],
                text=m["metadata"].get("text", ""),
                score=m["score"],
                metadata={**m["metadata"], "chapter_key": m["metadata"].get("chapter_key", chapter_key)},
                dense_score=m["score"],
            )
            for m in matches
            if m["metadata"].get("text")
        ]

    @staticmethod
    async def _sparse_one(
        namespace: str,
        chapter_key: str,
        query: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        sparse = _get_sparse(namespace)
        try:
            hits = await sparse.search(query, top_k)
        except Exception as e:
            logger.warning("Sparse search failed for %s: %s", namespace, e)
            return []

        return [
            _match_to_chunk(
                chunk_id=cid,
                text=text,
                score=score,
                # sparse_score = the bm25 raw score (we don't have a
                # good 0-1 normalization for it, so just use the rank
                # in RRF for the fused signal)
                metadata={**meta, "chapter_key": meta.get("chapter_key", chapter_key)},
                sparse_score=score,
            )
            for cid, text, meta, score in hits
        ]


# Module-level singleton (stateless, safe to share)
hybrid_retriever = HybridRetriever()
