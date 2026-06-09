"""
Cohere reranker (optional).

Only instantiated if a COHERE_API_KEY was provided in .env. The rag
pipeline imports `get_cohere_rerank` and calls it only when settings
indicate a key is present, so the rest of the app is unbothered.
"""

from __future__ import annotations
import logging
from typing import Any

import cohere

from config.settings import get_settings

logger = logging.getLogger(__name__)

_client: cohere.AsyncClient | None = None


def get_cohere() -> cohere.AsyncClient | None:
    """
    Return the Cohere async client, or None if no key is configured.
    Lazy — does nothing until the first successful call so importing
    this module never fails on a fresh dev install.
    """
    global _client
    s = get_settings()
    if not s.has_cohere:
        return None
    if _client is None:
        _client = cohere.AsyncClient(api_key=s.cohere_api_key)
        logger.info("Cohere client initialized (rerank model: rerank-english-v3.0)")
    return _client


async def rerank(
    query: str,
    documents: list[dict[str, Any]],
    *,
    top_n: int = 8,
) -> list[dict[str, Any]]:
    """
    Rerank retrieved chunks. `documents` is a list of dicts that must
    each contain a `text` field. Returns the same dicts (with their
    original metadata) reordered by Cohere relevance.
    """
    client = get_cohere()
    if client is None or not documents:
        return documents[:top_n]

    texts = [d["text"] for d in documents]
    response = await client.rerank(
        model="rerank-english-v3.0",
        query=query,
        documents=texts,
        top_n=min(top_n, len(texts)),
    )

    reranked = [documents[r.index] for r in response.results]
    logger.debug("Reranked %d → %d chunks", len(documents), len(reranked))
    return reranked
