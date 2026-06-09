/**
 * Server-only Supabase client. Used in Server Components, Route
 * Handlers, and middleware. Reads/writes the auth session via
 * Next.js cookies().
 *
 * NEVER import this from a client component — it pulls in
 * `next/headers` which throws at build time outside server context.
 */

import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";

import type { Database } from "./database.types";

export function getServerSupabase() {
  const cookieStore = cookies();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    throw new Error("Supabase env vars not set");
  }
  return createServerClient<Database>(url, key, {
    cookies: {
      get(name: string) {
        return cookieStore.get(name)?.value;
      },
      set(name: string, value: string, options: CookieOptions) {
        try {
          cookieStore.set({ name, value, ...options });
        } catch {
          // Called from a Server Component (read-only). Ignore —
          // the middleware refreshes the session.
        }
      },
      remove(name: string, options: CookieOptions) {
        try {
          cookieStore.set({ name, value: "", ...options });
        } catch {
          // same as above
        }
      },
    },
  });
}
