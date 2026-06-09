"""
OpenAI client wrapper — used for BOTH text completions (gpt-4o-mini) and
embeddings (text-embedding-3-small). All roles (classifier / answer /
ingestion) use gpt-4o-mini for now; this single file is the only place
that knows about the model names, so switching later is one constant.
"""

from __future__ import annotations
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from config.settings import get_settings

logger = logging.getLogger(__name__)

# Module-level singleton — the AsyncOpenAI client is safe to share
# across coroutines and manages its own connection pool.
_client: AsyncOpenAI | None = None


def get_openai() -> AsyncOpenAI:
    """Lazy-init the async OpenAI client using current settings."""
    global _client
    if _client is None:
        s = get_settings()
        _client = AsyncOpenAI(api_key=s.openai_api_key)
        logger.info(
            "OpenAI client initialized (text_model=%s, embed_model=%s, env=%s)",
            s.openai_text_model,
            s.openai_embedding_model,
            s.environment,
        )
    return _client


def get_model_for(role: str) -> str:
    """
    Look up the text model ID for a logical role
    ('classifier', 'answer', 'ingestion', 'vision'). Centralizes
    any future per-role model swap in one place.
    """
    s = get_settings()
    try:
        return s.models[role]
    except KeyError:
        raise ValueError(
            f"Unknown model role '{role}'. "
            f"Valid roles: {list(s.models.keys())}"
        )


# ─────────────────────────────────────────────────────────────────────────
# STREAMING TEXT COMPLETION
# Used by the answer generator — token-by-token SSE.
# ─────────────────────────────────────────────────────────────────────────
async def stream_chat(
    *,
    role: str,
    system: str,
    user: str,
    max_tokens: int = 2048,
    temperature: float = 0.3,
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[str]:
    """
    Stream text deltas from gpt-4o-mini.

    Optional `history` is a list of {"role": "user"|"assistant",
    "content": str} dicts for multi-turn conversation. When
    provided, each entry is inserted between the system message
    and the current user message in chronological order.
    """
    """
    Stream text deltas from gpt-4o-mini. Yields raw text fragments
    (not events) so the caller can wrap them in SSE however they like.

    OpenAI's chat format expects a list of {role, content} messages.
    We accept system + user separately and combine them — this lets the
    rest of the codebase keep the "system prompt + query" mental model
    that worked for Anthropic, while the actual API call is OpenAI-shaped.
    """
    client = get_openai()
    model = get_model_for(role)
    logger.debug("OpenAI stream: model=%s role=%s", model, role)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    # Multi-turn history: prior turns between system and the
    # current user message. Each entry must be {"role": ..., "content": ...}.
    for h in (history or []):
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user})

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )

    async for chunk in response:
        # Each chunk has a single delta; the `content` field may be None
        # for role-only deltas (which we ignore).
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


# ─────────────────────────────────────────────────────────────────────────
# NON-STREAMING TEXT COMPLETION
# Used for the classifier and any small structured-extraction tasks
# where streaming adds no value.
# ─────────────────────────────────────────────────────────────────────────
async def complete_chat(
    *,
    role: str,
    system: str,
    user: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> str:
    """
    Non-streaming completion. Returns the assistant text. Used for the
    classifier and small structured-extraction tasks where streaming
    adds no value.
    """
    client = get_openai()
    model = get_model_for(role)
    logger.debug("OpenAI complete: model=%s role=%s", model, role)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    if response.choices:
        return response.choices[0].message.content or ""
    return ""


# ─────────────────────────────────────────────────────────────────────────
# JSON MODE
# Used by the classifier and diagram processor — guarantees valid JSON
# output, no markdown fencing, no preamble to strip.
# ─────────────────────────────────────────────────────────────────────────
async def complete_chat_json(
    *,
    role: str,
    system: str,
    user: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> str:
    """
    Same as complete_chat but forces JSON-object output via
    response_format={"type": "json_object"}. The model still needs to
    be told (in the system prompt) what shape the JSON should take.
    """
    client = get_openai()
    model = get_model_for(role)
    logger.debug("OpenAI json: model=%s role=%s", model, role)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )

    if response.choices:
        return response.choices[0].message.content or ""
    return ""


# ─────────────────────────────────────────────────────────────────────────
# EMBEDDINGS
# 1536-d vectors from text-embedding-3-small, batched up to 100 per call.
# ─────────────────────────────────────────────────────────────────────────
async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of strings. Returns a list of 1536-d vectors in the
    same order as the input. Batches internally so callers can pass
    any length.
    """
    if not texts:
        return []

    s = get_settings()
    client = get_openai()
    BATCH = 100
    out: list[list[float]] = []

    for i in range(0, len(texts), BATCH):
        batch = texts[i:i + BATCH]
        # OpenAI replaces empty strings with a 1536-d zero vector
        # internally; we keep that behavior by passing them as-is.
        response = await client.embeddings.create(
            model=s.openai_embedding_model,
            input=batch,
        )
        out.extend([d.embedding for d in response.data])

    logger.debug("Embedded %d texts with %s", len(texts), s.openai_embedding_model)
    return out


async def get_embedding(text: str) -> list[float]:
    """Convenience: embed a single string."""
    vectors = await get_embeddings([text])
    return vectors[0]
