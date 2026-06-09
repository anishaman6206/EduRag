"""
Streaming answer generator.

Takes the reranked chunks + the original classification and yields SSE
events of the form:

    data: {"type": "token", "content": "..."}\\n\\n
    data: {"type": "diagrams", "data": [...]}\\n\\n
    data: {"type": "sources", "data": [...]}\\n\\n
    data: {"type": "done"}\\n\\n

The FastAPI route wraps this in a StreamingResponse with
media_type="text/event-stream".

Two important behaviors:
  1. Diagram chunks are STRIPPED from the LLM context. The model can't
     see images, so passing them as text would just confuse it. Instead
     we tell the model "Refer to the diagram below" via the system
     prompt, and ship the actual diagrams to the client as a separate
     SSE event after the text stream finishes.

  2. The LLM context is built from text-only chunks. For each text
     chunk we include the chapter name + page number so the model can
     cite sources naturally. Diagram chunks contribute no text to the
     LLM but their URLs go out in the diagrams event.
"""

from __future__ import annotations
import json
import logging
from typing import AsyncIterator

from config.constants import ANSWER_GENERATOR_PROMPT
from services.openai_service import stream_chat

from rag.classifier import Classification
from rag.retriever import RetrievedChunk
from rag.status import (
    get_status_emitter, reading_message,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Event helpers
# ─────────────────────────────────────────────────────────────────────────
def _sse(event: dict) -> str:
    """
    Encode one SSE event. FastAPI's StreamingResponse will hand each
    yielded string to the wire as-is. We include the double-newline
    that the SSE protocol requires to delimit events.
    """
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


async def _emit_status(message: str) -> str:
    """Encode a status event, or return empty string if no emitter set."""
    if not message:
        return ""
    return _sse({"type": "status", "message": message})


# ─────────────────────────────────────────────────────────────────────────
# Context building
# ─────────────────────────────────────────────────────────────────────────
def _build_text_context(
    text_chunks: list[RetrievedChunk],
    max_chars: int = 12000,
) -> str:
    """
    Assemble the context block for the LLM. Each chunk is rendered as:

        [Source: chapter_key, page N]
        <text>

    Capped at `max_chars` to keep the prompt small. We never split a
    chunk mid-sentence; if the next chunk would overflow the budget,
    we stop and let the model work with what it has.
    """
    if not text_chunks:
        return "(No relevant textbook content found.)"

    parts: list[str] = []
    used = 0
    for i, c in enumerate(text_chunks, start=1):
        chapter = c.chapter_key or "unknown chapter"
        page = f", p. {c.page}" if c.page is not None else ""
        block = f"[Source {i}: {chapter}{page}]\n{c.text}\n"

        if used + len(block) > max_chars and parts:
            # Budget exhausted; stop adding chunks. The model will
            # still have plenty to work with.
            break
        parts.append(block)
        used += len(block)

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────
# Public streaming function
# ─────────────────────────────────────────────────────────────────────────
async def stream_answer(
    query: str,
    chunks: list[RetrievedChunk],
    classification: Classification,
    *,
    source_language: str = "english",
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[str]:
    """
    Yield SSE event strings for the client's ReadableStream reader.

    The first token arrives in <500ms for gpt-4o-mini. The full
    answer is typically 200-500 tokens (~1-2s). Diagram and source
    events come at the end.

    `source_language` is the language tag the query refiner detected.
    The answer prompt uses it to reply in the same register — if
    the student asked in Hinglish, the answer comes back in Hinglish.

    `history` is a list of prior turns for multi-turn conversation
    context. Each entry is {"role": "user"|"assistant", "content": str}.
    The model sees the system prompt, then the history in order,
    then the current user message — standard OpenAI chat format.
    """
    # ── Split chunks: text → LLM context, diagrams → SSE event
    text_chunks = [c for c in chunks if not c.is_diagram]
    diagram_chunks = [c for c in chunks if c.is_diagram]

    context = _build_text_context(text_chunks)

    chapter_name = (
        classification.chapter_meta["display_name"]
        if classification.chapter_meta
        else classification.subject or "this subject"
    )

    system_prompt = ANSWER_GENERATOR_PROMPT.format(
        class_level=classification.class_level or "7-9",
        subject=classification.subject or "PCM",
        chapter_name=chapter_name,
        context=context,
        user_query=query,
        source_language=source_language,
    )

    # gpt-4o-mini takes a single user message. Combine the query and
    # the diagram hint into that one message.
    user_message = query
    if diagram_chunks:
        user_message += (
            "\n\n(Note: a relevant diagram from the textbook will be shown "
            "to the student separately. If you reference it in your "
            "answer, say \"Refer to the diagram below\".)"
        )

    # ── Stream tokens from the LLM
    # Emit a 'reading' status right before the first token, so the
    # user sees the pipeline progress even if the LLM takes a moment.
    yield await _emit_status(reading_message())

    token_count = 0
    try:
        async for delta in stream_chat(
            role="answer",
            system=system_prompt,
            user=user_message,
            max_tokens=1500,
            temperature=0.3,
            history=history,
        ):
            token_count += 1
            yield _sse({"type": "token", "content": delta})
    except Exception as e:
        logger.exception("LLM streaming failed: %s", e)
        yield _sse({"type": "error", "message": "Answer generation failed."})
        # Still emit a done so the client doesn't hang waiting
        yield _sse({"type": "done"})
        return

    # ── Emit diagrams (if any)
    if diagram_chunks:
        diagrams_payload = [
            {
                "url": c.diagram_url,
                "caption": c.text.split("\n")[0][:200] if c.text else "",
                "page": c.page,
                "chapter_key": c.chapter_key,
                "explanation": c.text,  # the full description from ingestion
            }
            for c in diagram_chunks
        ]
        yield _sse({"type": "diagrams", "data": diagrams_payload})

    # ── Emit sources (a short preview of each text chunk used)
    sources_payload = [
        {
            "chunk_id": c.id,
            "chapter_key": c.chapter_key,
            "page": c.page,
            "score": round(c.score, 4),
            "preview": (c.text[:200] + "…") if len(c.text) > 200 else c.text,
        }
        for c in chunks[:8]  # don't send the full list — 8 is plenty for the UI
    ]
    yield _sse({"type": "sources", "data": sources_payload})

    # ── Done
    logger.info(
        "streamed %d tokens, %d diagrams, %d sources for query=%r",
        token_count, len(diagram_chunks), len(sources_payload), query[:80],
    )
    yield _sse({"type": "done"})
