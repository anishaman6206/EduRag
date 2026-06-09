"""
POST /ask — the main RAG endpoint.

Flow:
  1. Validate the AskRequest (Pydantic).
  2. Check Redis cache for a previous answer. If hit, replay the
     stored SSE events directly (no LLM call).
  3. Run the pipeline: classify → retrieve → rerank (optional) →
     generate.
  4. Stream SSE events to the client.
  5. On completion (background task): save to Supabase, populate
     Redis cache.

SSE event types emitted:
  status    — friendly message ("Looking in Class 8 Science, Ch 4…")
  token     — incremental LLM output
  diagrams  — diagram chunks to render
  sources   — chunk citations
  done      — final marker
  error     — recoverable error (e.g. LLM rate-limited)
"""

from __future__ import annotations
import asyncio
import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from config.constants import NAMESPACE_MAP
from config.settings import get_settings
from models.request_models import AskRequest
from services import redis_service
from services.supabase_service import save_chat_message

from rag.classifier import classify_query, Classification
from rag.retriever import hybrid_retriever
from rag.reranker import rerank
from rag.generator import stream_answer
from rag.status import (
    set_status_emitter, get_status_emitter,
    thinking_message, looking_up_message, done_message,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────
# Helper: replay a cached answer as SSE events
# ─────────────────────────────────────────────────────────────────────────
async def _replay_cached(cached: dict) -> AsyncIterator[str]:
    """
    Turn a stored cached answer into the same SSE stream a live
    /ask would have produced. Used when Redis has a cache hit.
    """
    cached_text = cached.get("answer", "")
    cached_diagrams = cached.get("diagrams", [])
    cached_sources = cached.get("sources", [])

    # Same status event the live path would have fired
    yield f"data: {json.dumps({'type': 'status', 'message': done_message()})}\n\n"

    # Replay the answer as a single 'token' event (not split into
    # many small ones — the client just appends to its message bubble)
    if cached_text:
        yield f"data: {json.dumps({'type': 'token', 'content': cached_text})}\n\n"

    if cached_diagrams:
        yield f"data: {json.dumps({'type': 'diagrams', 'data': cached_diagrams})}\n\n"
    if cached_sources:
        yield f"data: {json.dumps({'type': 'sources', 'data': cached_sources})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ─────────────────────────────────────────────────────────────────────────
# Helper: status event emitter that yields into the SSE stream
# ─────────────────────────────────────────────────────────────────────────
def _make_status_emitter(queue: asyncio.Queue) -> "asyncio.Queue":
    """
    Returns a coroutine that puts a status message into the queue.
    The streaming generator reads from the queue and yields the
    corresponding SSE event. This decouples the pipeline phases
    (which run sequentially) from the SSE stream (which yields as
    soon as anything is ready).

    Why a queue and not just yielding directly:
    The pipeline functions (classifier, retriever) return values
    rather than yielding — they're not async generators. We need
    to inject 'status' events between them without restructuring
    the whole pipeline. The emitter pushes into a queue; the
    generator side pulls + yields.
    """
    async def _emit(message: str) -> None:
        await queue.put({"type": "status", "message": message})
    return _emit


# ─────────────────────────────────────────────────────────────────────────
# Main streaming generator
# ─────────────────────────────────────────────────────────────────────────
async def _stream_pipeline(
    request: AskRequest,
    user_id: str,
) -> AsyncIterator[str]:
    """
    Runs the full RAG pipeline and yields SSE events. The actual
    FastAPI route wraps this in a StreamingResponse.
    """
    t0 = time.monotonic()
    status_queue: asyncio.Queue = asyncio.Queue()
    # _make_status_emitter returns a coroutine, not an awaitable that
    # needs awaiting here — call it as a plain function and register
    # the resulting coroutine as the emitter.
    set_status_emitter(_make_status_emitter(status_queue))

    # Helper: drain any pending status events, yielding them as SSE
    async def _drain_status() -> list[str]:
        out: list[str] = []
        while not status_queue.empty():
            payload = status_queue.get_nowait()
            out.append(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")
        return out

    # ── Phase: think (no work yet, just acknowledge the user)
    thinking = thinking_message(request.query)
    yield f"data: {json.dumps({'type': 'status', 'message': thinking})}\n\n"

    # ── Cache check
    cache_key = redis_service.make_cache_key(
        request.query, request.class_level or "", request.subject,
    )
    try:
        cached = await redis_service.cache_get(cache_key)
        if cached:
            logger.info("Cache hit for %s", cache_key)
            for s in await _drain_status():
                yield s
            async for event in _replay_cached(cached):
                yield event
            set_status_emitter(None)
            return
    except Exception as e:
        logger.warning("Cache get failed (proceeding without cache): %s", e)

    # ── OPTIMIZATION: skip the classifier when the user has already
    # supplied both subject and class. Synthesize a Classification
    # from the pre-filter values and skip the gpt-4o-mini LLM call
    # entirely. Saves 1.5-3s on warm path.
    #
    # If only one of the two is supplied, we still need the
    # classifier to fill in the missing field.
    # If neither is supplied, we use the classifier to decide
    # everything.
    from services.openai_service import get_embedding as _get_embedding
    try:
        if request.subject and request.class_level:
            # Fast path: user pre-filtered. Build a "no specific
            # chapter, but we know the subject+class" classification.
            classification = Classification(
                subject=request.subject,
                class_level=request.class_level,
                chapter_key=None,  # will search all matching chapters
                confidence=1.0,
                chapter_meta=None,
            )
            query_vector = await _get_embedding(request.query)
        else:
            # Slow path: need the classifier. Run it in parallel
            # with the embed call.
            async def _do_classify():
                return await classify_query(
                    request.query,
                    hint_subject=request.subject,
                    hint_class=request.class_level,
                )
            async def _do_embed():
                return await _get_embedding(request.query)
            classification, query_vector = await asyncio.gather(
                _do_classify(), _do_embed()
            )
    except Exception as e:
        logger.exception("Classifier/embed failed: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'message': 'Could not understand the question. Please try again.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        set_status_emitter(None)
        return

    # Drain any statuses fired during classification
    for s in await _drain_status():
        yield s
    # Always fire the 'looking up' message after classification
    looking = looking_up_message(classification)
    yield f"data: {json.dumps({'type': 'status', 'message': looking})}\n\n"

    # ── Phase: retrieve (use the pre-computed query vector).
    # Top_k=20 (was 10) because the answer benefits from more
    # context, and the reranker (if Cohere is enabled) will
    # cut it down to the best 8 anyway. With 39 namespaces in
    # play now, pulling more per-namespace helps when the user
    # asks a broad question without a filter.
    try:
        chunks = await hybrid_retriever.retrieve(
            request.query,
            classification,
            top_k=20,
            query_vector=query_vector,  # pass it in to skip re-embedding
        )
    except Exception as e:
        logger.exception("Retriever failed: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'message': 'Search failed. Please try again.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        set_status_emitter(None)
        return

    # ── Phase: rerank (optional)
    s = get_settings()
    if s.has_cohere and chunks:
        try:
            chunks = await rerank(request.query, chunks, top_n=8)
        except Exception as e:
            logger.warning("Rerank failed (using retriever order): %s", e)

    # Drain any pending statuses
    for s in await _drain_status():
        yield s

    if not chunks:
        # No relevant content found. Don't call the LLM with empty
        # context — give the student a clear, honest response.
        yield f"data: {json.dumps({'type': 'token', 'content': 'I could not find this in your textbook. Could you rephrase the question, or specify which chapter it belongs to?'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        set_status_emitter(None)
        return

    # ── Phase: generate (streams tokens)
    full_answer_parts: list[str] = []
    final_diagrams: list[dict] = []
    final_sources: list[dict] = []

    try:
        async for sse_event in stream_answer(
            request.query,
            chunks,
            classification,
        ):
            # Capture the answer as it streams for caching later.
            # 'token' events carry the LLM output.
            if '"type": "token"' in sse_event:
                try:
                    payload = json.loads(sse_event[6:].strip())
                    if payload.get("type") == "token":
                        full_answer_parts.append(payload.get("content", ""))
                except Exception:
                    pass
            elif '"type": "diagrams"' in sse_event:
                try:
                    payload = json.loads(sse_event[6:].strip())
                    final_diagrams = payload.get("data", [])
                except Exception:
                    pass
            elif '"type": "sources"' in sse_event:
                try:
                    payload = json.loads(sse_event[6:].strip())
                    final_sources = payload.get("data", [])
                except Exception:
                    pass
            yield sse_event
    except Exception as e:
        logger.exception("Generator failed: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'message': 'Answer generation failed. Please try again.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        set_status_emitter(None)
        return

    set_status_emitter(None)
    logger.info(
        "/ask: query=%r → %d tokens, %d diagrams, %d sources, %.2fs",
        request.query[:60],
        sum(len(p) for p in full_answer_parts),
        len(final_diagrams), len(final_sources),
        time.monotonic() - t0,
    )

    # ── Cache + persist (background — don't block the response close)
    full_answer = "".join(full_answer_parts)
    asyncio.create_task(_persist_and_cache(
        user_id=user_id,
        request=request,
        classification=classification,
        chunks=chunks,
        full_answer=full_answer,
        diagrams=final_diagrams,
        sources=final_sources,
        cache_key=cache_key,
    ))

    # Helper: drain any pending status events, yielding them as SSE
    async def _drain_status() -> list[str]:
        out: list[str] = []
        while not status_queue.empty():
            payload = status_queue.get_nowait()
            out.append(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")
        return out

    # ── Phase: think (no work yet, just acknowledge the user)
    thinking = thinking_message(request.query)
    yield f"data: {json.dumps({'type': 'status', 'message': thinking})}\n\n"

    # ── Cache check
    cache_key = redis_service.make_cache_key(
        request.query, request.class_level or "", request.subject,
    )
    try:
        cached = await redis_service.cache_get(cache_key)
        if cached:
            logger.info("Cache hit for %s", cache_key)
            # Drain any pending statuses first
            for s in await _drain_status():
                yield s
            async for event in _replay_cached(cached):
                yield event
            set_status_emitter(None)
            return
    except Exception as e:
        logger.warning("Cache get failed (proceeding without cache): %s", e)

    # ── Phase: classify
    try:
        classification = await classify_query(
            request.query,
            hint_subject=request.subject,
            hint_class=request.class_level,
        )
    except Exception as e:
        logger.exception("Classifier failed: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'message': 'Could not understand the question. Please try again.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        set_status_emitter(None)
        return

    # Drain any statuses fired during classification
    for s in await _drain_status():
        yield s
    # Always fire the 'looking up' message after classification
    looking = looking_up_message(classification)
    yield f"data: {json.dumps({'type': 'status', 'message': looking})}\n\n"

    # ── Phase: retrieve
    try:
        chunks = await hybrid_retriever.retrieve(
            request.query,
            classification,
            top_k=10,
        )
    except Exception as e:
        logger.exception("Retriever failed: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'message': 'Search failed. Please try again.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        set_status_emitter(None)
        return

    # ── Phase: rerank (optional)
    s = get_settings()
    if s.has_cohere and chunks:
        try:
            chunks = await rerank(request.query, chunks, top_n=8)
        except Exception as e:
            logger.warning("Rerank failed (using retriever order): %s", e)

    # Drain any pending statuses
    for s in await _drain_status():
        yield s

    if not chunks:
        # No relevant content found. Don't call the LLM with empty
        # context — give the student a clear, honest response.
        yield f"data: {json.dumps({'type': 'token', 'content': 'I could not find this in your textbook. Could you rephrase the question, or specify which chapter it belongs to?'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        set_status_emitter(None)
        return

    # ── Phase: generate (streams tokens)
    full_answer_parts: list[str] = []
    final_diagrams: list[dict] = []
    final_sources: list[dict] = []

    try:
        async for sse_event in stream_answer(
            request.query,
            chunks,
            classification,
        ):
            # Capture the answer as it streams for caching later.
            # 'token' events carry the LLM output.
            if '"type": "token"' in sse_event:
                try:
                    payload = json.loads(sse_event[6:].strip())
                    if payload.get("type") == "token":
                        full_answer_parts.append(payload.get("content", ""))
                except Exception:
                    pass
            elif '"type": "diagrams"' in sse_event:
                try:
                    payload = json.loads(sse_event[6:].strip())
                    final_diagrams = payload.get("data", [])
                except Exception:
                    pass
            elif '"type": "sources"' in sse_event:
                try:
                    payload = json.loads(sse_event[6:].strip())
                    final_sources = payload.get("data", [])
                except Exception:
                    pass
            yield sse_event
    except Exception as e:
        logger.exception("Generator failed: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'message': 'Answer generation failed. Please try again.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        set_status_emitter(None)
        return

    set_status_emitter(None)
    logger.info(
        "/ask: query=%r → %d tokens, %d diagrams, %d sources, %.2fs",
        request.query[:60],
        sum(len(p) for p in full_answer_parts),
        len(final_diagrams), len(final_sources),
        time.monotonic() - t0,
    )

    # ── Cache + persist (background — don't block the response close)
    full_answer = "".join(full_answer_parts)
    asyncio.create_task(_persist_and_cache(
        user_id=user_id,
        request=request,
        classification=classification,
        chunks=chunks,
        full_answer=full_answer,
        diagrams=final_diagrams,
        sources=final_sources,
        cache_key=cache_key,
    ))


async def _persist_and_cache(
    *,
    user_id: str,
    request: AskRequest,
    classification,
    chunks,
    full_answer: str,
    diagrams: list[dict],
    sources: list[dict],
    cache_key: str,
) -> None:
    """
    Run AFTER the SSE stream is done. Best-effort: failures are
    logged but never surface to the user.
    """
    # Cache the full answer for next time
    try:
        await redis_service.cache_set(
            cache_key,
            {
                "answer": full_answer,
                "diagrams": diagrams,
                "sources": sources,
            },
            ttl_seconds=3600,
        )
    except Exception as e:
        logger.warning("Cache set failed: %s", e)

    # Save to Supabase chat history
    try:
        sources_for_db = [
            {
                "chunk_id": c.id,
                "chapter_key": c.chapter_key,
                "page": c.page,
                "score": round(c.score, 4),
            }
            for c in chunks[:8]
        ]
        await save_chat_message({
            "user_id": user_id,
            "class_level": request.class_level or (classification.class_level if classification else None),
            "subject": request.subject or (classification.subject if classification else None),
            "chapter_key": classification.chapter_key if classification else None,
            "query": request.query,
            "answer": full_answer,
            "sources": sources_for_db,
        })
    except Exception as e:
        logger.warning("Save chat_message failed: %s", e)


# ─────────────────────────────────────────────────────────────────────────
# Route handler
# ─────────────────────────────────────────────────────────────────────────
@router.post("/ask")
async def ask(request: Request, body: AskRequest) -> StreamingResponse:
    """
    Main RAG endpoint. Streams the answer as Server-Sent Events.

    The client (frontend) consumes the stream using a ReadableStream
    reader (see useStream.ts) and dispatches events by type.
    """
    user_id = body.user_id or "anonymous"

    # Note: we do NOT use FastAPI's dependency-injection validation
    # for streaming; we just call the generator.
    return StreamingResponse(
        _stream_pipeline(body, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
