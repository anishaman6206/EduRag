"use client";

/**
 * ChatWindow — the main chat container.
 *
 * Layout:
 *   [ Sidebar (history) | Chat area ]
 *                          - Header: filters + new conversation
 *                          - Messages (auto-scroll)
 *                          - Input bar
 *
 * History sidebar:
 *   - List of past conversation threads (newest first)
 *   - Click to load that thread's messages
 *   - "New conversation" button at the top — resets the
 *     localStorage conversation_id and clears the chat
 *
 * Filters (top of chat area):
 *   - Class dropdown
 *   - Subject dropdown
 *   - Chapter dropdown (populated from /chapters, filtered by
 *     selected class+subject)
 */

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";

import { useChatStore } from "@/store/chatStore";
import { useStream } from "@/hooks/useStream";
import { useAuth } from "@/hooks/useAuth";
import { MessageBubble } from "./MessageBubble";
import { QueryInput } from "./QueryInput";
import { SubjectClassFilter } from "@/components/Filters/SubjectClassFilter";
import { HistorySidebar } from "./HistorySidebar";
import {
  listChapters,
  listConversations,
  getConversationMessages,
  type Chapter,
  type ConversationSummary,
} from "@/lib/api";
import type { ClassLevel, Subject, ChatMessage } from "@/lib/types";

function uuid(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function getOrCreateConversationId(): string {
  if (typeof window === "undefined") return "ssr";
  let cid = window.localStorage.getItem("edurag:conversation_id");
  if (!cid) {
    cid = uuid();
    window.localStorage.setItem("edurag:conversation_id", cid);
  }
  return cid;
}

export function ChatWindow() {
  const auth = useAuth();
  const store = useChatStore();
  const { sendQuery, cancel, isStreaming } = useStream();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Conversation state
  const [conversationId, setConversationId] = useState<string>("");
  useEffect(() => {
    setConversationId(getOrCreateConversationId());
  }, []);

  // Filters
  const [classLevel, setClassLevel] = useState<ClassLevel | "">("");
  const [subject, setSubject] = useState<Subject | "" | "all">("all");
  const [chapterKey, setChapterKey] = useState<string>("");
  const [chapters, setChapters] = useState<Chapter[]>([]);

  // History sidebar
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);

  const userId = auth.user?.id || "anonymous";

  // Fetch chapters when filters change
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cs = await listChapters({
          class_level: classLevel || undefined,
          subject: subject === "all" ? undefined : (subject || undefined),
        });
        if (!cancelled) {
          setChapters(cs);
          // If the currently-selected chapter_key is no longer in
          // the filtered list, clear it.
          if (chapterKey && !cs.find((c) => c.chapter_key === chapterKey)) {
            setChapterKey("");
          }
        }
      } catch (e) {
        console.warn("listChapters failed:", e);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classLevel, subject]);

  // Fetch conversation list when the sidebar opens (and on first
  // mount). Refreshes when the store changes (so a new message
  // updates the sidebar after a delay).
  const refreshConversations = useCallback(async () => {
    if (!userId || userId === "anonymous") {
      setConversations([]);
      return;
    }
    try {
      const cs = await listConversations(userId);
      setConversations(cs);
    } catch (e) {
      console.warn("listConversations failed:", e);
    }
  }, [userId]);

  useEffect(() => {
    if (sidebarOpen) {
      refreshConversations();
    }
  }, [sidebarOpen, refreshConversations, store.messages.length]);

  // Auto-scroll to bottom on new content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [store.messages, store.status]);

  function handleSubmit(text: string) {
    // Read the conversation_id directly from localStorage here,
    // not from React state. The state is initialized in a
    // useEffect which runs after the first render — meaning the
    // very first message the user sends would otherwise be sent
    // with conversation_id="". The /ask route would still process
    // it (no error) but Supabase would save the row with
    // conversation_id=NULL, which the history sidebar then can't
    // display.
    const cid = typeof window !== "undefined"
      ? (window.localStorage.getItem("edurag:conversation_id") || getOrCreateConversationId())
      : conversationId;
    sendQuery(text, {
      class_level: classLevel || undefined,
      subject: subject === "all" ? undefined : (subject || undefined),
      chapter_key: chapterKey || undefined,
      conversation_id: cid,
    });
    // Refresh conversations after a moment so the new thread shows
    // up in the sidebar.
    setTimeout(() => refreshConversations(), 1500);
  }

  function startNewConversation() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("edurag:conversation_id");
    }
    const newId = uuid();
    if (typeof window !== "undefined") {
      window.localStorage.setItem("edurag:conversation_id", newId);
    }
    setConversationId(newId);
    setActiveConversationId(null);
    store.reset();
    setSidebarOpen(false);
  }

  async function loadConversation(convId: string) {
    setActiveConversationId(convId);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("edurag:conversation_id", convId);
    }
    setConversationId(convId);
    try {
      const rows = await getConversationMessages(convId, userId);
      // Convert DB rows → ChatMessage[] for the store
      const msgs: ChatMessage[] = rows.flatMap((r) => [
        {
          id: `${r.id}-q`,
          role: "user" as const,
          content: r.query,
          created_at: r.created_at,
        },
        {
          id: `${r.id}-a`,
          role: "assistant" as const,
          content: r.answer,
          sources: r.sources ?? undefined,
          created_at: r.created_at,
        },
      ]);
      store.reset();
      for (const m of msgs) store.appendMessage(m);
    } catch (e) {
      console.warn("loadConversation failed:", e);
    }
    setSidebarOpen(false);
  }

  return (
    <div className="flex h-screen bg-gray-50 flex-col lg:flex-row">
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}
      
      {/* Sidebar — hidden on mobile unless toggled */}
      <div className={`fixed inset-y-0 left-0 z-50 w-72 transition-transform lg:static lg:translate-x-0 ${
        sidebarOpen ? "translate-x-0" : "-translate-x-full"
      }`}>
        {sidebarOpen && (
          <HistorySidebar
            conversations={conversations}
            activeConversationId={activeConversationId}
            onSelect={loadConversation}
            onNew={startNewConversation}
            onClose={() => setSidebarOpen(false)}
          />
        )}
      </div>

      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <header className="flex items-center justify-between gap-1 px-3 sm:px-4 py-2.5 sm:py-3 border-b border-gray-200 bg-white sticky top-0 z-30">
          <div className="flex items-center gap-1 sm:gap-2 min-w-0 flex-1">
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              aria-label="Toggle history"
              className="p-1.5 rounded-md hover:bg-gray-100 text-gray-600 lg:hidden flex-shrink-0"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <button
              onClick={startNewConversation}
              className="px-2 sm:px-3 py-1.5 text-xs sm:text-sm border border-gray-300 rounded-md hover:bg-gray-50 flex items-center gap-1 flex-shrink-0"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span className="hidden sm:inline">New chat</span>
            </button>
            <Link href="/" className="text-base sm:text-lg font-bold text-gray-900 truncate">
              EduRag
            </Link>
            <span className="text-xs text-gray-400 hidden sm:inline">NCERT doubt solver</span>
          </div>

          <div className="flex items-center gap-1 sm:gap-2 flex-wrap justify-end">
            <div className="hidden sm:flex gap-1">
              <SubjectClassFilter
                classLevel={classLevel}
                subject={subject}
                onChange={(next) => {
                  setClassLevel(next.classLevel);
                  setSubject(next.subject);
                }}
                disabled={isStreaming}
              />
            </div>
            <select
              aria-label="Chapter"
              value={chapterKey}
              onChange={(e) => setChapterKey(e.target.value)}
              disabled={isStreaming || chapters.length === 0}
              className="text-xs sm:text-sm border border-gray-300 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50 max-w-[100px] sm:max-w-[180px] truncate"
              title={chapters.find((c) => c.chapter_key === chapterKey)?.display_name ?? ""}
            >
              <option value="">All chapters</option>
              {chapters.map((c) => (
                <option key={c.chapter_key} value={c.chapter_key}>
                  {c.display_name}
                </option>
              ))}
            </select>
            {auth.user ? (
              <button
                onClick={() => auth.signOut()}
                className="text-xs sm:text-sm text-gray-600 hover:text-gray-900 px-1 sm:px-2"
              >
                Sign out
              </button>
            ) : (
              <Link
                href="/login"
                className="text-xs sm:text-sm px-2 sm:px-3 py-1 sm:py-1.5 bg-brand-600 text-white rounded-md hover:bg-brand-700 whitespace-nowrap"
              >
                Sign in
              </Link>
            )}
          </div>
        </header>

        {/* Messages */}
        <main className="flex-1 overflow-y-auto px-2 sm:px-4 py-4 sm:py-6 space-y-3 sm:space-y-4">
          {store.messages.length === 0 && <EmptyState />}
          {store.messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {store.error && (
            <div className="max-w-2xl sm:max-w-3xl mx-auto rounded-lg bg-red-50 border border-red-200 p-2.5 sm:p-3 text-xs sm:text-sm text-red-700 w-full">
              {store.error}
            </div>
          )}
          <div ref={messagesEndRef} />
        </main>

        {/* Input bar */}
        <footer className="border-t border-gray-200 bg-white px-2 sm:px-4 py-2.5 sm:py-3 sticky bottom-0">
          <div className="max-w-2xl sm:max-w-3xl mx-auto flex items-end gap-1.5 sm:gap-2">
            <div className="flex-1">
              <QueryInput
                onSubmit={handleSubmit}
                disabled={isStreaming}
                placeholder="Ask a doubt from your NCERT textbook… (Ctrl+Enter to send)"
              />
            </div>
            {isStreaming && (
              <button
                onClick={cancel}
                className="px-2 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 flex-shrink-0 whitespace-nowrap"
              >
                Stop
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="max-w-xl sm:max-w-2xl mx-auto text-center pt-8 sm:pt-16 px-3">
      <div className="text-4xl sm:text-5xl mb-3 sm:mb-4">📚</div>
      <h1 className="text-xl sm:text-2xl font-bold text-gray-900 mb-1.5 sm:mb-2">
        Ask a doubt from your NCERT textbook
      </h1>
      <p className="text-xs sm:text-sm text-gray-500 mb-3 sm:mb-6 leading-relaxed">
        I'm your friendly tutor, grounded in Class 8 NCERT science. I'll cite the exact chapter and page number, and pull in diagrams from your book.
      </p>
      <div className="text-xs text-brand-700 bg-brand-50 border border-brand-200 rounded-lg px-2.5 sm:px-3 py-2 mb-4 sm:mb-6 inline-block">
        💡 <strong>Tip:</strong> Pick a chapter first for faster answers.
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
        {SAMPLE_PROMPTS.map((p) => (
          <div
            key={p}
            className="px-2.5 sm:px-3 py-2 bg-white border border-gray-200 rounded-lg text-xs sm:text-sm text-gray-600 line-clamp-2"
          >
            "{p}"
          </div>
        ))}
      </div>
    </div>
  );
}

const SAMPLE_PROMPTS = [
  "What is an electric circuit?",
  "How do forces affect motion?",
  "What is the difference between acids and bases?",
  "force kya hai? (Hinglish)",
  "Aur detail mein batao ek example ke saath",
];
