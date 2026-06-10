"""
backfill_conversation_ids.py — one-shot migration.

When the conversation_id column was added to chat_messages, all
existing rows had NULL. The history sidebar uses
.mode=conversations which filters out NULL rows, so those
chats were invisible.

This script backfills NULL rows with a synthetic conversation_id
derived from `user_id + first_query` hash. The result: all of
one user's NULL messages get grouped into the SAME synthetic
thread, so the sidebar shows them as one conversation.

Run once after applying the schema.sql conversation_id
migration:

    PYTHONPATH=backend python scripts/backfill_conversation_ids.py
"""

import asyncio
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.supabase_service import get_supabase


async def main():
    c = get_supabase()
    res = c.table("chat_messages").select("id, user_id, query, created_at") \
        .is_("conversation_id", "null") \
        .order("created_at", desc=False) \
        .limit(2000) \
        .execute()
    rows = res.data or []
    print(f"Rows needing backfill: {len(rows)}")

    if not rows:
        print("Nothing to do.")
        return

    # Group by user. We want all of one user's NULL rows in the same
    # synthetic thread (so the sidebar shows them as one
    # conversation, in chronological order).
    by_user: dict[str, list[dict]] = {}
    for row in rows:
        by_user.setdefault(row["user_id"], []).append(row)

    updates = 0
    for user_id, user_rows in by_user.items():
        first = user_rows[0]
        # Synthetic id derived from user + their first question. The
        # hash means the same user + same first question always gets
        # the same id (idempotent if the script is run twice).
        synthetic = "backfill-" + hashlib.md5(
            f"{user_id}:{first['query']}".encode()
        ).hexdigest()[:12]

        for row in user_rows:
            upd = c.table("chat_messages").update(
                {"conversation_id": synthetic}
            ).eq("id", row["id"]).execute()
            if upd.data:
                updates += 1

    print(f"Backfilled {updates} rows with synthetic conversation_ids.")
    print(f"  Distinct user-threads: {len(by_user)}")
    print()
    print("Refresh the history sidebar in the browser to see them.")


if __name__ == "__main__":
    asyncio.run(main())
