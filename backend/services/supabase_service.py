"""
Supabase client — handles two responsibilities:
  1. PostgreSQL writes (chat history, parent-chunk storage)
  2. Supabase Storage (diagram image uploads → public URLs)

The `supabase-py` SDK is sync internally; we wrap the calls but do not
add async overhead at the network layer — Python's GIL releases during
the socket read, which is the dominant cost.
"""

from __future__ import annotations
import logging
from typing import Any
from supabase import create_client, Client

from config.settings import get_settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_supabase() -> Client:
    """Lazy-init Supabase client using service-role key (server-side)."""
    global _client
    if _client is None:
        s = get_settings()
        _client = create_client(s.supabase_url, s.supabase_service_key)
        logger.info("Supabase client initialized (url=%s)", s.supabase_url)
    return _client


# ─────────────────────────────────────────────────────────────────────────
# CHAT HISTORY (table: chat_messages)
# Columns expected: id (uuid), user_id (text), class_level (text),
#                  subject (text), chapter_key (text), query (text),
#                  answer (text), sources (jsonb), created_at (timestamptz)
# ─────────────────────────────────────────────────────────────────────────
async def save_chat_message(record: dict[str, Any]) -> dict[str, Any]:
    """Insert a row into chat_messages. Returns the inserted row."""
    client = get_supabase()
    response = client.table("chat_messages").insert(record).execute()
    if not response.data:
        raise RuntimeError("Supabase insert returned no data")
    return response.data[0]


async def get_chat_history(
    *,
    user_id: str,
    limit: int = 50,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch the most recent N messages for a user, newest first.
    If conversation_id is provided, restrict to that thread.
    """
    client = get_supabase()
    query = client.table("chat_messages").select("*").eq("user_id", user_id)
    if conversation_id:
        query = query.eq("conversation_id", conversation_id)
    response = query.order("created_at", desc=True).limit(limit).execute()
    return response.data or []


async def get_conversation_history(
    *,
    user_id: str,
    conversation_id: str,
    limit: int = 6,
    max_chars_per_turn: int = 1500,
) -> list[dict[str, str]]:
    """
    Fetch the last N turns of a conversation in chronological order
    (oldest first). Used by the /ask route to build multi-turn
    context for the generator prompt.

    Returns a list of {"role": "user"|"assistant", "content": str}
    dicts. Long assistant answers are truncated to
    `max_chars_per_turn` chars to keep the prompt small.
    """
    client = get_supabase()
    response = (
        client.table("chat_messages")
        .select("role, query, answer, created_at")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(limit + 1)  # +1 to skip the in-flight assistant msg
        .execute()
    )
    rows = list(reversed(response.data or []))

    out: list[dict[str, str]] = []
    for r in rows:
        if r.get("query"):
            out.append({"role": "user", "content": r["query"]})
        if r.get("answer"):
            ans = r["answer"]
            if len(ans) > max_chars_per_turn:
                ans = ans[:max_chars_per_turn] + "…"
            out.append({"role": "assistant", "content": ans})
    return out[-limit * 2:]  # cap total tokens roughly


async def list_conversations(
    *,
    user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    List the most recent N conversation threads for a user, newest
    first. Returns one row per conversation with:
      - conversation_id
      - first_query (the student's opening question in that thread)
      - last_message_at (timestamp of the most recent message)
      - message_count

    Used by the frontend's history sidebar.
    """
    from sqlalchemy import text  # not used; placeholder
    client = get_supabase()
    # Supabase-py doesn't have a great GROUP BY helper, so we fetch
    # recent rows and aggregate in Python. Fine for a chat app at this
    # scale (a few hundred messages per user max).
    response = (
        client.table("chat_messages")
        .select("conversation_id, query, created_at")
        .eq("user_id", user_id)
        .not_.is_("conversation_id", "null")
        .order("created_at", desc=True)
        .limit(500)  # safety cap — covers ~50 conversations
        .execute()
    )
    rows = response.data or []

    # Group by conversation_id, keep first + last + count
    seen: dict[str, dict[str, Any]] = {}
    for r in rows:
        cid = r.get("conversation_id")
        if not cid:
            continue
        if cid not in seen:
            seen[cid] = {
                "conversation_id": cid,
                "first_query": r.get("query", ""),
                "last_message_at": r.get("created_at"),
                "message_count": 0,
            }
        seen[cid]["message_count"] += 1
        # 'first_query' is the OLDEST query in the thread (since we
        # fetched DESC). Capture from the LAST row we see for this cid.
        if r.get("query"):
            seen[cid]["first_query"] = r.get("query", seen[cid]["first_query"])

    # Sort by last_message_at DESC
    out = sorted(seen.values(), key=lambda x: x["last_message_at"], reverse=True)
    return out[:limit]


async def get_messages_by_conversation(
    *,
    user_id: str,
    conversation_id: str,
) -> list[dict[str, Any]]:
    """Full chat_messages rows for one conversation, oldest first."""
    client = get_supabase()
    response = (
        client.table("chat_messages")
        .select("*")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )
    return response.data or []


# ─────────────────────────────────────────────────────────────────────────
# PARENT CHUNKS (table: parent_chunks)
# Columns expected: id (uuid), chapter_key (text), content (text),
#                  token_count (int), metadata (jsonb), created_at
# ─────────────────────────────────────────────────────────────────────────
async def save_parent_chunk(record: dict[str, Any]) -> dict[str, Any]:
    """
    Upsert a parent chunk by id. On re-ingest the same parent will
    have the same id (content hash is deterministic) and we just
    overwrite. Avoids the 'duplicate key' error from a plain insert.
    """
    client = get_supabase()
    response = (
        client.table("parent_chunks")
        .upsert(record, on_conflict="id")
        .execute()
    )
    return response.data[0] if response.data else {}


async def get_parent_chunk(parent_id: str) -> dict[str, Any] | None:
    client = get_supabase()
    response = (
        client.table("parent_chunks")
        .select("*")
        .eq("id", parent_id)
        .maybe_single()
        .execute()
    )
    return response.data


# ─────────────────────────────────────────────────────────────────────────
# STORAGE — diagram images live in bucket 'diagrams' (create once in
# the Supabase dashboard, mark it Public so URLs are shareable).
# ─────────────────────────────────────────────────────────────────────────
DIAGRAM_BUCKET = "diagrams"


async def upload_diagram(
    *,
    storage_path: str,    # e.g. "physics/class_9/physics_9_ch9_motion/fig_181_a1b2c3d4.png"
    image_bytes: bytes,
    content_type: str = "image/png",
) -> str:
    """
    Upload a diagram image and return the public URL.
    `storage_path` is the full key inside the bucket (no leading slash).
    """
    client = get_supabase()
    client.storage.from_(DIAGRAM_BUCKET).upload(
        path=storage_path,
        file=image_bytes,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    public_url = client.storage.from_(DIAGRAM_BUCKET).get_public_url(storage_path)
    logger.info("Uploaded diagram: %s", storage_path)
    return public_url
