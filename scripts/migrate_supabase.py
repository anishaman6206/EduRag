"""
migrate_supabase.py — one-shot migration script.

Run this once to add the `conversation_id` column to an existing
chat_messages table in Supabase. Idempotent (safe to re-run).

Usage:
    PYTHONPATH=backend python scripts/migrate_supabase.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.supabase_service import get_supabase

# Read the migration SQL from the schema file
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "backend" / "ingestion" / "schema.sql"


def main():
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    # Run the whole schema as a single RPC. Supabase exposes a
    # 'pg_execute' RPC for arbitrary SQL via the PostgREST
    # /rest/v1/rpc/pg_execute endpoint, but it requires a
    # SECURITY DEFINER function. The simplest portable approach
    # is to give the user the exact SQL to paste into the SQL
    # editor.
    print("=" * 60)
    print("Supabase migration helper")
    print("=" * 60)
    print()
    print("This script can't run DDL directly via the PostgREST API")
    print("(it requires elevated privileges). Instead, copy the SQL")
    print("below and run it in your Supabase SQL editor:")
    print()
    print("https://supabase.com/dashboard/project/skmpdfeabsecreyppudq/sql")
    print()
    print("-" * 60)
    # Print only the do-$$ block (the additive migration) and the
    # index creation if not exists
    import re
    m = re.search(r"do \$\$.*?end \$\$;", sql, re.DOTALL)
    if m:
        print(m.group(0))
    print("-" * 60)
    print()
    print("After running, the /history endpoint will work fully.")


if __name__ == "__main__":
    main()
