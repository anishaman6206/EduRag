/**
 * Chat store — holds the list of messages, the streaming state,
 * and the current status banner. Centralized in a Zustand store so
 * multiple components (sidebar, message list, status banner) can
 * read+write the same state without prop-drilling.
 */

"use client";

import { create } from "zustand";
import type { ChatMessage, AskRequest } from "@/lib/types";

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  status: string | null;
  error: string | null;
  abortController: AbortController | null;

  // Actions
  setStatus: (status: string | null) => void;
  setError: (error: string | null) => void;
  appendMessage: (msg: ChatMessage) => void;
  /**
   * Update the most recent message. Accepts either a partial patch
   * OR a function that receives the previous message and returns a
   * new one. The function form is needed for "append to content"
   * because the patch form can't read the previous value.
   */
  updateLastMessage: (
    patch: Partial<ChatMessage> | ((prev: ChatMessage) => Partial<ChatMessage>),
  ) => void;
  setStreaming: (streaming: boolean) => void;
  setAbortController: (controller: AbortController | null) => void;
  cancel: () => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  status: null,
  error: null,
  abortController: null,

  setStatus: (status) => set({ status }),
  setError: (error) => set({ error }),
  appendMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateLastMessage: (patch) =>
    set((s) => {
      if (s.messages.length === 0) return s;
      const last = s.messages[s.messages.length - 1];
      const partial = typeof patch === "function" ? patch(last) : patch;
      return { messages: [...s.messages.slice(0, -1), { ...last, ...partial }] };
    }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setAbortController: (abortController) => set({ abortController }),
  cancel: () => {
    const ctrl = get().abortController;
    if (ctrl) ctrl.abort();
    set({ isStreaming: false, status: null, abortController: null });
  },
  reset: () =>
    set({
      messages: [],
      isStreaming: false,
      status: null,
      error: null,
      abortController: null,
    }),
}));
