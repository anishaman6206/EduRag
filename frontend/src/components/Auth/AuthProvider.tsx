"use client";

/**
 * AuthProvider — wraps the app and exposes the current user via
 * useAuth(). Manages the Supabase auth session:
 *  - On mount, calls getUser() to populate the initial state.
 *  - Subscribes to onAuthStateChange so sign-in / sign-out from
 *    any tab updates the UI here.
 *  - Exposes signInWithEmail, signInWithGoogle, signOut helpers.
 *
 * Google OAuth is enabled by default — the project owner has
 * configured the Google provider in the Supabase dashboard. If
 * you ever need to disable it without redeploying, set
 * NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=false in your env.
 */

import { useEffect, useState, type ReactNode } from "react";
import type { User } from "@supabase/supabase-js";
import { getBrowserSupabase } from "@/lib/supabase-browser";
import { AuthContext, type AuthContextValue } from "@/hooks/useAuth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Google OAuth is always available — the user has configured it
  // in their Supabase dashboard. To disable without a redeploy,
  // set NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=false in your env.
  const googleEnabled = process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED !== "false";

  useEffect(() => {
    let mounted = true;

    // 1. Initial session
    (async () => {
      try {
        const { data } = await getBrowserSupabase().auth.getUser();
        if (mounted) setUser(data.user ?? null);
      } catch (e) {
        // Supabase env not set yet — keep user null
        console.warn("auth.getUser failed:", e);
      } finally {
        if (mounted) setLoading(false);
      }
    })();

    // 2. Subscribe to changes (sign-in, sign-out, token refresh)
    const { data: sub } = getBrowserSupabase().auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user ?? null);
      },
    );

    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const value: AuthContextValue = {
    user,
    loading,
    googleEnabled,
    async signInWithEmail(email) {
      try {
        const { error } = await getBrowserSupabase().auth.signInWithOtp({
          email,
          options: {
            emailRedirectTo: `${window.location.origin}/chat`,
          },
        });
        return { error: error?.message ?? null };
      } catch (e) {
        return { error: (e as Error).message };
      }
    },
    async signInWithGoogle() {
      try {
        const { error } = await getBrowserSupabase().auth.signInWithOAuth({
          provider: "google",
          options: {
            redirectTo: `${window.location.origin}/chat`,
          },
        });
        return { error: error?.message ?? null };
      } catch (e) {
        return { error: (e as Error).message };
      }
    },
    async signOut() {
      await getBrowserSupabase().auth.signOut();
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
