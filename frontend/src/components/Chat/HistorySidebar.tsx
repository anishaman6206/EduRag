"use client";

/**
 * HistorySidebar — left-side drawer showing past conversation
 * threads. Mirrors the ChatGPT-style history pattern.
 *
 * Props:
 *   conversations:        list of threads (newest first)
 *   activeConversationId: the thread the user is currently viewing
 *   onSelect:             click handler — load that thread
 *   onNew:                start a fresh conversation
 *   onClose:              close the drawer (mobile)
 *
 * The "anonymous" user has no history (no /history rows). For
 * that case the sidebar shows a friendly nudge to sign in.
 */

import type { ConversationSummary } from "@/lib/api";

interface Props {
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  onSelect: (conversationId: string) => void;
  onNew: () => void;
  onClose: () => void;
}

export function HistorySidebar({
  conversations,
  activeConversationId,
  onSelect,
  onNew,
  onClose,
}: Props) {
  return (
    <aside className="w-72 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-700">History</h2>
        <div className="flex items-center gap-1">
          <button
            onClick={onNew}
            aria-label="New conversation"
            title="Start a new conversation"
            className="p-1.5 rounded-md hover:bg-gray-100 text-gray-600"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
          <button
            onClick={onClose}
            aria-label="Close history"
            title="Close"
            className="p-1.5 rounded-md hover:bg-gray-100 text-gray-600 lg:hidden"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">
            <p>No conversations yet.</p>
            <p className="mt-2 text-xs">
              Sign in to keep your history across devices. Without sign-in, history is
              stored per-tab only and is lost on browser refresh.
            </p>
          </div>
        ) : (
          <ul className="py-2">
            {conversations.map((conv) => {
              const isActive = conv.conversation_id === activeConversationId;
              const title = conv.first_query || "(no question)";
              const dateLabel = formatDate(conv.last_message_at);
              return (
                <li key={conv.conversation_id}>
                  <button
                    onClick={() => onSelect(conv.conversation_id)}
                    className={
                      "w-full text-left px-3 py-2.5 hover:bg-gray-50 border-l-2 transition " +
                      (isActive
                        ? "bg-brand-50 border-brand-500"
                        : "border-transparent")
                    }
                  >
                    <div className="text-sm text-gray-800 line-clamp-2 font-medium">
                      {title}
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                      <span>{dateLabel}</span>
                      <span>·</span>
                      <span>{conv.message_count} msg</span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
    if (sameDay) {
      return d.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      });
    }
    const sameYear = d.getFullYear() === now.getFullYear();
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: sameYear ? undefined : "numeric",
    });
  } catch {
    return "";
  }
}
