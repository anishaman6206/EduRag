"""
Optional Cohere rerank step.

If COHERE_API_KEY is set in .env, take the top RETRIEVAL_TOP_K chunks
from the retriever and rerank them with rerank-english-v3.0, returning
the top RERANK_TOP_K. If the key is missing, return the input list
unchanged (capped at RERANK_TOP_K) so the pipeline runs identically
with or without Cohere.

Why optional?
- Cohere isn't free.
- For many queries, the retriever's hybrid RRF ranking is already
  good enough that rerank adds latency without changing the answer.
- The skip is silent — the user gets the same experience, just a
  bit less precise.
"""

from __future__ import annotations
import logging

from config.constants import RETRIEVAL_TOP_K, RERANK_TOP_K
from config.settings import get_settings
from services.cohere_service import get_cohere, rerank as cohere_rerank
from rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


async def rerank(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    top_n: int = RERANK_TOP_K,
) -> list[RetrievedChunk]:
    """
    Rerank `chunks` for `query` using Cohere. Returns the top `top_n`.

    If Cohere isn't configured, returns `chunks[:top_n]` unchanged.
    """
    if not chunks:
        return []

    settings = get_settings()
    if not settings.has_cohere:
        # Silent skip — the pipeline works without a Cohere key
        return chunks[:top_n]

    cohere_client = get_cohere()
    if cohere_client is None:
        return chunks[:top_n]

    # Cohere rerank takes the document text. We pass the same text
    # the retriever stored in `text`. For diagram chunks the text is
    # the LLM-generated description, which is exactly what we want
    # to rerank on.
    documents = [{"id": c.id, "text": c.text} for c in chunks]

    try:
        response = await cohere_client.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=documents,
            top_n=min(top_n, len(documents)),
        )
    except Exception as e:
        logger.warning("Cohere rerank failed, falling back to retriever order: %s", e)
        return chunks[:top_n]

    # Re-order chunks per Cohere's ranking. Each result has an `index`
    # pointing into our input `chunks` list and a `relevance_score`.
    reranked: list[RetrievedChunk] = []
    for r in response.results:
        chunk = chunks[r.index]
        # Update the chunk's `score` to the rerank score so any
        # downstream consumer sees the new signal. Keep dense/sparse
        # intact for debugging.
        chunk = RetrievedChunk(
            id=chunk.id, text=chunk.text, score=float(r.relevance_score),
            dense_score=chunk.dense_score, sparse_score=chunk.sparse_score,
            chapter_key=chunk.chapter_key, class_level=chunk.class_level,
            subject=chunk.subject, content_type=chunk.content_type,
            parent_id=chunk.parent_id, page=chunk.page,
            chunk_index=chunk.chunk_index, diagram_url=chunk.diagram_url,
            extra={**chunk.extra, "rerank_score": float(r.relevance_score)},
        )
        reranked.append(chunk)

    logger.info("Reranked %d → %d chunks (Cohere enabled)", len(chunks), len(reranked))
    return reranked
