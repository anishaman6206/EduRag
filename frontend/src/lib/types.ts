/**
 * Shared TypeScript types. Mirrors the backend Pydantic models +
 * the SSE event shapes from rag/generator.py.
 */

// ─────────────────────────────────────────────────────────────────────────
// Domain types
// ─────────────────────────────────────────────────────────────────────────
export type Subject = "math" | "physics" | "chemistry" | "biology";
export type ClassLevel = "7" | "8" | "9" | "10";

export interface Chapter {
  key: string;            // e.g. "physics_8_ch4"
  display_name: string;   // "Electricity: Magnetic and Heating Effects"
  class_level: ClassLevel;
  subject: Subject;
  chapter_number: number;
}

// ─────────────────────────────────────────────────────────────────────────
// SSE event types from /ask
// ─────────────────────────────────────────────────────────────────────────
export type AskEvent =
  | { type: "status"; message: string }
  | { type: "token"; content: string }
  | { type: "diagrams"; data: DiagramPayload[] }
  | { type: "sources"; data: SourcePayload[] }
  | { type: "error"; message: string }
  | { type: "done" };

export interface DiagramPayload {
  url: string;
  caption: string;
  page: number;
  chapter_key: string;
  explanation: string;
}

export interface SourcePayload {
  chunk_id: string;
  chapter_key: string;
  page: number | null;
  score: number;
  preview: string;
}

// ─────────────────────────────────────────────────────────────────────────
// /ask request body
// ─────────────────────────────────────────────────────────────────────────
export interface AskRequest {
  query: string;
  class_level?: ClassLevel;
  subject?: Subject;
  user_id?: string;
  conversation_id?: string;
  history?: { role: "user" | "assistant"; content: string }[];
}

// ─────────────────────────────────────────────────────────────────────────
// /history response
// ─────────────────────────────────────────────────────────────────────────
export interface HistoryItem {
  id: string;
  user_id: string;
  class_level: ClassLevel | null;
  subject: Subject | null;
  chapter_key: string | null;
  query: string;
  answer: string;
  sources: SourcePayload[] | null;
  created_at: string;
}

// ─────────────────────────────────────────────────────────────────────────
// /health response
// ─────────────────────────────────────────────────────────────────────────
export interface HealthCheck {
  status: "ok" | "degraded" | "error";
  detail: string | null;
}
export interface HealthResponse {
  status: "ok" | "degraded";
  checks: Record<string, HealthCheck>;
}

// ─────────────────────────────────────────────────────────────────────────
// Chat message — what the UI renders. One per (student, AI) turn.
// ─────────────────────────────────────────────────────────────────────────
export interface ChatMessage {
  id: string;                   // local uuid
  role: "user" | "assistant";
  content: string;              // user query, or accumulated AI text
  status?: string;              // current "thinking..." status from SSE
  diagrams?: DiagramPayload[];
  sources?: SourcePayload[];
  created_at: string;
  isStreaming?: boolean;        // true while AI is still streaming
  error?: string;
}
