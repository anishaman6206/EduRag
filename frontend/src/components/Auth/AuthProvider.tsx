"use client";

/**
 * AuthProvider — wraps the app and exposes the current user via
 * useAuth(). Manages the Supabase auth session:
 *  - On mount, calls getUser() to populate the initial state.
 *  - Subscribes to onAuthStateChange so sign-in / sign-out from
 *    any tab updates the UI here.
 *  - Exposes signInWithEmail, signInWithGoogle, signOut helpers.
 */

import { useEffect, useState, type ReactNode } from "react";
import type { User } from "@supabase/supabase-js";
import { getBrowserSupabase } from "@/lib/supabase-browser";
import { AuthContext, type AuthContextValue } from "@/hooks/useAuth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [googleEnabled, setGoogleEnabled] = useState(false);

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

    // 1b. Probe whether Google is enabled. We try signInWithOAuth and
    // catch the "provider is not enabled" error. If we get it, we hide
    // the Google button in the login page so users don't see a
    // broken button. Any other error is treated as "enabled" (the
    // real error will surface when the user actually clicks).
    (async () => {
      try {
        const { error } = await getBrowserSupabase().auth.signInWithOAuth({
          provider: "google",
          options: { skipBrowserRedirect: true } as any,
        });
        // Most likely: error message about needing a session —
        // that's OK, Google IS enabled, we just can't actually sign in
        // without going through the OAuth flow. Only treat
        // "provider is not enabled" as disabled.
        if (error && /provider is not enabled/i.test(error.message)) {
          if (mounted) setGoogleEnabled(false);
        } else {
          if (mounted) setGoogleEnabled(true);
        }
      } catch {
        if (mounted) setGoogleEnabled(false);
      }
    })();

    // 2. Subscribe to changes
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
