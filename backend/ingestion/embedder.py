"""
Embedder — thin wrapper around the OpenAI service for the ingestion
pipeline. Kept as a separate file so the ingestion layer has a stable
import path (`from ingestion.embedder import embed_texts`) that doesn't
change if we later swap embedding providers.
"""

from __future__ import annotations
import logging
from typing import Iterable

from services.openai_service import get_embeddings

logger = logging.getLogger(__name__)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of strings. Returns 1536-d vectors in the same order
    as the input. Batching is handled inside the OpenAI service.

    Empty strings are passed through (OpenAI returns a 1536-d zero
    vector for them, which is fine — the chunker should never produce
    empty children, but defensive).
    """
    if not texts:
        return []
    vectors = await get_embeddings(texts)
    logger.debug("Embedded %d texts", len(texts))
    return vectors


async def embed_text(text: str) -> list[float]:
    """Convenience: embed a single string."""
    vectors = await embed_texts([text])
    return vectors[0]
