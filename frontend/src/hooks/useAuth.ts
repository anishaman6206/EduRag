/**
 * useAuth hook — gives every component access to the current user
 * and the sign-in / sign-out methods.
 *
 * Auth state is held in a small React context (AuthProvider in
 * components/Auth/AuthProvider.tsx). This hook just reads it.
 */

"use client";

import { createContext, useContext } from "react";
import type { User } from "@supabase/supabase-js";

export interface AuthContextValue {
  user: User | null;
  loading: boolean;
  signInWithEmail: (email: string) => Promise<{ error: string | null }>;
  signInWithGoogle: () => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  signInWithEmail: async () => ({ error: "AuthProvider not mounted" }),
  signInWithGoogle: async () => ({ error: "AuthProvider not mounted" }),
  signOut: async () => {},
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
