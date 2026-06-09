/**
 * Browser-only Supabase client. Used by AuthProvider and any
 * client component that needs to read the current session.
 *
 * Kept separate from supabase-server.ts so the latter can import
 * `next/headers` without dragging the import graph into the
 * client bundle.
 */

"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { Database } from "./database.types";

let _client: ReturnType<typeof createBrowserClient<Database>> | null = null;

export function getBrowserSupabase() {
  if (!_client) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!url || !key) {
      throw new Error("Supabase env vars not set — copy .env.local.example to .env.local");
    }
    _client = createBrowserClient<Database>(url, key);
  }
  return _client;
}
