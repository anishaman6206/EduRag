/**
 * useStream — wraps streamAsk() with React state. Call sendQuery()
 * to start a stream; the hook returns nothing but updates the chat
 * store (useChatStore) as events arrive.
 *
 * Why a hook + store instead of just returning events:
 *  - The chat window is composed of multiple components (status
 *    banner, message list, sources panel). They all need to react
 *    to the same stream. Centralizing the state in a store means
 *    they all subscribe and stay in sync.
 *  - Aborting mid-stream needs to be possible from any component
 *    (e.g. the user clicks "Stop"). The store holds the
 *    AbortController so all components can reach it.
 */

"use client";

import { useCallback } from "react";
import { streamAsk } from "@/lib/api";
import { useChatStore } from "@/store/chatStore";
import { useAuth } from "./useAuth";
import type { AskRequest, ChatMessage } from "@/lib/types";

function uuid(): string {
  // Tiny uuid-v4 shim — fine for client-side keys, not for crypto.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function useStream() {
  const auth = useAuth();
  const store = useChatStore();

  const sendQuery = useCallback(
    async (query: string, filters: { class_level?: string; subject?: string } = {}) => {
      if (store.isStreaming) return;
      if (!query.trim()) return;

      const userId = auth.user?.id || "anonymous";

      // Stable per-tab conversation id (stored in localStorage). Groups
      // all turns in this browser tab into one conversation thread
      // so the backend can fetch the prior N turns for multi-turn
      // context. Surviving page refreshes means a student can
      // close/reopen the tab and pick up where they left off.
      let conversationId: string | undefined;
      if (typeof window !== "undefined") {
        conversationId = window.localStorage.getItem("edurag:conversation_id") || undefined;
        if (!conversationId) {
          conversationId = uuid();
          window.localStorage.setItem("edurag:conversation_id", conversationId);
        }
      }

      // 1. Append the user message immediately
      const userMsg: ChatMessage = {
        id: uuid(),
        role: "user",
        content: query,
        created_at: new Date().toISOString(),
      };
      store.appendMessage(userMsg);

      // 2. Append a placeholder assistant message that we'll fill in
      const aiMsg: ChatMessage = {
        id: uuid(),
        role: "assistant",
        content: "",
        status: "Thinking…",
        created_at: new Date().toISOString(),
        isStreaming: true,
      };
      store.appendMessage(aiMsg);

      // 3. Start streaming
      const controller = new AbortController();
      store.setAbortController(controller);
      store.setStreaming(true);
      store.setStatus("Thinking…");
      store.setError(null);

      const body: AskRequest = {
        query,
        user_id: userId,
        conversation_id: conversationId,
        class_level: filters.class_level as AskRequest["class_level"],
        subject: filters.subject as AskRequest["subject"],
      };

      try {
        for await (const evt of streamAsk(body, { signal: controller.signal })) {
          switch (evt.type) {
            case "status":
              store.setStatus(evt.message);
              store.updateLastMessage({ status: evt.message });
              break;

            case "token":
              store.setStatus(null);
              store.updateLastMessage((prev: ChatMessage) => ({
                ...prev,
                content: prev.content + evt.content,
                status: undefined,
              }));
              break;

            case "diagrams":
              store.updateLastMessage({ diagrams: evt.data });
              break;

            case "sources":
              store.updateLastMessage({ sources: evt.data, isStreaming: false });
              break;

            case "error":
              store.setError(evt.message);
              store.updateLastMessage({
                error: evt.message,
                isStreaming: false,
              });
              break;

            case "done":
              store.updateLastMessage({ isStreaming: false });
              break;
          }
        }
      } catch (e) {
        const msg = (e as Error).message;
        // AbortError is expected when the user clicks "Stop"
        if (msg.includes("abort")) {
          store.updateLastMessage({ isStreaming: false, status: undefined });
        } else {
          store.setError(msg);
          store.updateLastMessage({
            error: msg,
            isStreaming: false,
            status: undefined,
          });
        }
      } finally {
        store.setStreaming(false);
        store.setStatus(null);
        store.setAbortController(null);
      }
    },
    [auth.user?.id, store],
  );

  return { sendQuery, cancel: store.cancel, isStreaming: store.isStreaming, status: store.status, error: store.error };
}
