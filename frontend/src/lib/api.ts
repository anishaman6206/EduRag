/**
 * Typed API client. All calls go through the Next.js rewrite
 * /api/backend/* → http://localhost:8000/*, so the browser never
 * has to deal with CORS preflights.
 */

import type {
  AskEvent,
  AskRequest,
  HealthResponse,
  HistoryItem,
} from "./types";

const API_BASE =
  typeof window !== "undefined"
    ? `http://${window.location.hostname}:8000`
    : "/api/backend";

/**
 * Send a question to /ask and return an async iterator of SSE events.
 *
 * Uses the fetch ReadableStream API to read chunks as they arrive
 * from the server, parses each `data: {json}` line, and yields the
 * decoded event. Caller is responsible for consuming the iterator
 * and updating UI state.
 */
export async function* streamAsk(
  body: AskRequest,
  options: { signal?: AbortSignal } = {},
): AsyncGenerator<AskEvent, void, undefined> {
  const response = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`/ask failed: HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by \n\n. Split on that boundary.
      const events = buffer.split("\n\n");
      // The last element is either empty (if buffer ended on \n\n)
      // or an incomplete event we'll keep for the next chunk.
      buffer = events.pop() ?? "";

      for (const evt of events) {
        const line = evt.trim();
        if (!line.startsWith("data:")) continue;
        const json = line.slice(5).trim();
        if (!json) continue;
        try {
          const parsed = JSON.parse(json) as AskEvent;
          yield parsed;
        } catch (e) {
          console.warn("Failed to parse SSE event:", json, e);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * GET /history — fetch recent chat history for a user.
 */
export async function getHistory(
  userId: string,
  limit = 50,
): Promise<HistoryItem[]> {
  const url = new URL(`${API_BASE}/history`, window.location.origin);
  url.searchParams.set("user_id", userId);
  url.searchParams.set("limit", String(limit));
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`/history failed: HTTP ${res.status}`);
  }
  return (await res.json()) as HistoryItem[];
}

/**
 * GET /health — for the small status indicator in the UI.
 */
export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) {
    throw new Error(`/health failed: HTTP ${res.status}`);
  }
  return (await res.json()) as HealthResponse;
}

/**
 * GET /chapters — list available NCERT chapters.
 * Used to populate the chapter filter dropdown.
 */
export interface Chapter {
  chapter_key: string;
  display_name: string;
  class_level: string;
  subject: string;
  chapter_number: number;
}

export async function listChapters(filters?: {
  class_level?: string;
  subject?: string;
}): Promise<Chapter[]> {
  const url = new URL(`${API_BASE}/chapters`, window.location.origin);
  if (filters?.class_level) url.searchParams.set("class_level", filters.class_level);
  if (filters?.subject) url.searchParams.set("subject", filters.subject);
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`/chapters failed: HTTP ${res.status}`);
  }
  return (await res.json()) as Chapter[];
}

/**
 * GET /history?mode=conversations — list conversation threads.
 */
export interface ConversationSummary {
  conversation_id: string;
  first_query: string;
  last_message_at: string;
  message_count: number;
}

export async function listConversations(userId: string): Promise<ConversationSummary[]> {
  const url = new URL(`${API_BASE}/history`, window.location.origin);
  url.searchParams.set("user_id", userId);
  url.searchParams.set("mode", "conversations");
  url.searchParams.set("limit", "50");
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`/history?mode=conversations failed: HTTP ${res.status}`);
  }
  return (await res.json()) as ConversationSummary[];
}

/**
 * GET /history?conversation_id=X — full messages for one thread,
 * oldest first.
 */
export async function getConversationMessages(conversationId: string, userId: string): Promise<HistoryItem[]> {
  const url = new URL(`${API_BASE}/history`, window.location.origin);
  url.searchParams.set("user_id", userId);
  url.searchParams.set("conversation_id", conversationId);
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`/history?conversation_id failed: HTTP ${res.status}`);
  }
  return (await res.json()) as HistoryItem[];
}
