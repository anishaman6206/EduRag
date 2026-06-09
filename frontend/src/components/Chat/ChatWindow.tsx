"use client";

/**
 * ChatWindow — the main chat container. Composes:
 *  - Filter bar (SubjectClassFilter)
 *  - Scrollable message list (auto-scrolls to bottom on new content)
 *  - QueryInput at the bottom
 *  - Stop button while a stream is in progress
 *
 * Pulls everything from useChatStore. The actual streaming is
 * triggered by useStream.sendQuery().
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { useChatStore } from "@/store/chatStore";
import { useStream } from "@/hooks/useStream";
import { useAuth } from "@/hooks/useAuth";
import { MessageBubble } from "./MessageBubble";
import { QueryInput } from "./QueryInput";
import { SubjectClassFilter } from "@/components/Filters/SubjectClassFilter";
import type { ClassLevel, Subject } from "@/lib/types";

export function ChatWindow() {
  const auth = useAuth();
  const store = useChatStore();
  const { sendQuery, cancel, isStreaming } = useStream();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [classLevel, setClassLevel] = useState<ClassLevel | "">("");
  const [subject, setSubject] = useState<Subject | "" | "all">("all");

  // Auto-scroll to bottom on new content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [store.messages, store.status]);

  function handleSubmit(text: string) {
    sendQuery(text, {
      class_level: classLevel || undefined,
      subject: subject === "all" ? undefined : (subject || undefined),
    });
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-lg font-bold text-gray-900">
            EduRag
          </Link>
          <span className="text-xs text-gray-400">NCERT doubt solver</span>
        </div>
        <div className="flex items-center gap-3">
          <SubjectClassFilter
            classLevel={classLevel}
            subject={subject}
            onChange={(next) => {
              setClassLevel(next.classLevel);
              setSubject(next.subject);
            }}
            disabled={isStreaming}
          />
          {auth.user ? (
            <button
              onClick={() => auth.signOut()}
              className="text-sm text-gray-600 hover:text-gray-900"
            >
              Sign out
            </button>
          ) : (
            <Link
              href="/login"
              className="text-sm px-3 py-1.5 bg-brand-600 text-white rounded-md hover:bg-brand-700"
            >
              Sign in
            </Link>
          )}
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {store.messages.length === 0 && <EmptyState />}
        {store.messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {store.error && (
          <div className="max-w-3xl mx-auto rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {store.error}
          </div>
        )}
        <div ref={messagesEndRef} />
      </main>

      {/* Input bar */}
      <footer className="border-t border-gray-200 bg-white px-4 py-3">
        <div className="max-w-3xl mx-auto flex items-end gap-2">
          <div className="flex-1">
            <QueryInput
              onSubmit={handleSubmit}
              disabled={isStreaming}
              placeholder="Ask a doubt… (Ctrl+Enter to send)"
            />
          </div>
          {isStreaming && (
            <button
              onClick={cancel}
              className="px-3 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Stop
            </button>
          )}
        </div>
      </footer>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="max-w-2xl mx-auto text-center pt-16">
      <div className="text-5xl mb-4">📚</div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">
        Ask a doubt from your NCERT textbook
      </h1>
      <p className="text-sm text-gray-500 mb-6">
        I'm an AI tutor grounded in Class 7-10 NCERT. I'll cite the exact
        chapter and page number, and pull in diagrams from your book.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
        {SAMPLE_PROMPTS.map((p) => (
          <div
            key={p}
            className="px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-600"
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
  "Explain Newton's second law with an example.",
];
