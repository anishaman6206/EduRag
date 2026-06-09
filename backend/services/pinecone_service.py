"""
Pinecone vector DB client.

We use a namespace-per-chapter strategy: every chapter in NAMESPACE_MAP
maps to its own Pinecone namespace, so a query for Class 9 Motion can
never accidentally pull chunks from Class 7 Heat. Metadata is used for
secondary filtering (subject / class / content_type).
"""

from __future__ import annotations
import logging
from typing import Any

from pinecone import Pinecone, ServerlessSpec

from config.settings import get_settings

logger = logging.getLogger(__name__)

# Module-level singletons
_pc: Pinecone | None = None
_index = None


def get_pinecone() -> Pinecone:
    """Lazy-init the Pinecone client."""
    global _pc
    if _pc is None:
        s = get_settings()
        _pc = Pinecone(api_key=s.pinecone_api_key)
        logger.info("Pinecone client initialized (index=%s)", s.pinecone_index_name)
    return _pc


def get_index():
    """
    Return the configured index, creating it on first use if it does not
    exist. The dimension is hard-coded to 1536 (text-embedding-3-small)
    — change here AND in constants.EMBEDDING_DIM if the model is swapped.
    """
    global _index
    if _index is None:
        s = get_settings()
        pc = get_pinecone()

        existing = {idx.name for idx in pc.list_indexes()}
        if s.pinecone_index_name not in existing:
            logger.info("Creating Pinecone index '%s' (dim=1536, metric=cosine)",
                        s.pinecone_index_name)
            pc.create_index(
                name=s.pinecone_index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )

        _index = pc.Index(s.pinecone_index_name)

    return _index


async def upsert_vectors(
    namespace: str,
    vectors: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Upsert vectors into a namespace.

    Each vector dict must have: id, values, metadata.
    Re-ingesting the same IDs overwrites — no duplicates (idempotent).
    """
    if not vectors:
        return {"upserted": 0}

    index = get_index()
    # Pinecone Python SDK is sync; the network call is fast enough
    # that we don't bother with a thread pool. Batch at 100 per call.
    BATCH = 100
    total = 0
    for i in range(0, len(vectors), BATCH):
        batch = vectors[i:i + BATCH]
        index.upsert(vectors=batch, namespace=namespace)
        total += len(batch)

    logger.info("Upserted %d vectors to namespace='%s'", total, namespace)
    return {"upserted": total}


async def query_namespace(
    namespace: str,
    vector: list[float],
    *,
    top_k: int = 20,
    filter: dict[str, Any] | None = None,
    include_metadata: bool = True,
) -> list[dict[str, Any]]:
    """
    Run a dense vector query in a single namespace. Returns a list of
    match dicts: [{id, score, metadata}, ...].
    """
    index = get_index()
    response = index.query(
        namespace=namespace,
        vector=vector,
        top_k=top_k,
        filter=filter,
        include_metadata=include_metadata,
    )
    return [
        {
            "id": m.id,
            "score": float(m.score),
            "metadata": dict(m.metadata) if m.metadata else {},
        }
        for m in response.matches
    ]


async def delete_namespace(namespace: str) -> None:
    """
    Wipe a namespace. Used by the ingestion pipeline's rollback path
    when a chapter ingest fails partway through.
    """
    index = get_index()
    index.delete(delete_all=True, namespace=namespace)
    logger.warning("Rolled back namespace='%s'", namespace)


async def fetch_existing_hashes(
    namespace: str,
    candidate_ids: list[str],
) -> dict[str, str]:
    """
    For incremental ingest: return {chunk_id: version_hash} for every
    id in `candidate_ids` that ALREADY exists in the namespace. We
    fetch in batches of 100 (Pinecone limit). Ids not in the namespace
    are simply absent from the returned dict.
    """
    if not candidate_ids:
        return {}

    index = get_index()
    out: dict[str, str] = {}
    BATCH = 100
    try:
        for i in range(0, len(candidate_ids), BATCH):
            batch = candidate_ids[i:i + BATCH]
            response = index.fetch(ids=batch, namespace=namespace)
            for vec_id, vec in (response.vectors or {}).items():
                md = dict(vec.metadata or {})
                out[vec_id] = md.get("version_hash", "")
    except Exception as e:
        logger.warning("fetch_existing_hashes failed for %s: %s", namespace, e)
    return out


async def delete_vectors_by_id(namespace: str, ids: list[str]) -> None:
    """Delete specific vectors by id. Used for incremental cleanup."""
    if not ids:
        return
    index = get_index()
    BATCH = 100
    for i in range(0, len(ids), BATCH):
        batch = ids[i:i + BATCH]
        index.delete(ids=batch, namespace=namespace)
    logger.info("Deleted %d stale vectors from namespace='%s'", len(ids), namespace)
