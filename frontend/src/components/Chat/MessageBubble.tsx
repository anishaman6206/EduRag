"use client";

/**
 * MessageBubble — one chat message.
 *
 * User messages: right-aligned, brand-colored bubble, plain text.
 * AI messages: left-aligned, white card, with:
 *   - Markdown body (text + LaTeX + Mermaid diagrams)
 *   - Status banner while streaming ("Looking in Class 8 Science…")
 *   - Animated cursor + streaming dots while tokens are arriving
 *   - DiagramCards for each textbook diagram
 *   - Collapsible Sources section
 */

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

import type { ChatMessage } from "@/lib/types";
import { DiagramCard } from "@/components/Diagram/DiagramCard";
import { SourceCard } from "@/components/UI/SourceCard";
import { MermaidBlock } from "@/components/UI/MermaidBlock";
import { StreamingDots } from "./StreamingDots";
import { remarkMermaid } from "./remarkMermaid";

/**
 * Extract a mermaid code block from the children of a <p> element
 * that was produced by remark-mermaid. Returns the code if the
 * children contain a single text node matching the marker pattern,
 * or null otherwise.
 */
function extractMermaidCode(children: React.ReactNode): string | null {
  // Walk the children to find a text node starting with our marker.
  const marker = "__MERMAID_BLOCK__";
  const end = "__END__";
  const visit = (node: unknown): string | null => {
    if (typeof node === "string") {
      if (node.startsWith(marker) && node.endsWith(end)) {
        return node.slice(marker.length, node.length - end.length);
      }
      return null;
    }
    if (Array.isArray(node)) {
      // We want a SINGLE text child that is the whole marker payload.
      // If there are multiple children or any non-text, we don't
      // match (the paragraph wasn't produced by remark-mermaid).
      if (node.length !== 1) return null;
      return visit(node[0]);
    }
    // React element — skip; we only care about raw text.
    return null;
  };
  return visit(children);
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end w-full">
        <div className="max-w-xs sm:max-w-sm md:max-w-md bg-brand-600 text-white rounded-2xl rounded-tr-md px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    );
  }

  return <AssistantBubble message={message} />;
}

function AssistantBubble({ message }: { message: ChatMessage }) {
  const [showSources, setShowSources] = useState(false);

  return (
    <div className="flex justify-start w-full">
      <div className="max-w-sm sm:max-w-md md:max-w-2xl lg:max-w-3xl w-full bg-white border border-gray-200 rounded-2xl rounded-tl-md px-3 sm:px-5 py-2.5 sm:py-3 shadow-sm">
        {/* Status banner (visible while streaming) */}
        {message.status && (
          <div className="flex items-center gap-2 text-xs text-brand-700 mb-2">
            <span className="h-2 w-2 rounded-full bg-brand-500 animate-pulse" />
            {message.status}
          </div>
        )}

        {/* Error state */}
        {message.error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {message.error}
          </div>
        )}

        {/* Markdown body with LaTeX + Mermaid diagrams. We render
            even an empty body (just the streaming cursor) so the
            bubble has a stable height while tokens arrive. */}
        {message.content || message.isStreaming ? (
          <div className="prose-message">
            <ReactMarkdown
              remarkPlugins={[remarkMath, remarkMermaid]}
              rehypePlugins={[rehypeKatex]}
              components={{
                // The remark-mermaid plugin turns ```mermaid blocks
                // into paragraphs whose only text child is
                // "__MERMAID_BLOCK__<code>__END__". Intercept those
                // and render MermaidBlock instead.
                p: ({ children, ...rest }) => {
                  // children may be a single string or an array of
                  // elements — we only intercept when it's a string
                  // matching our marker.
                  const code = extractMermaidCode(children);
                  if (code !== null) {
                    return <MermaidBlock code={code} />;
                  }
                  return <p {...rest}>{children}</p>;
                },
              }}
            >
              {message.content || ""}
            </ReactMarkdown>
            {message.isStreaming && message.content && (
              <span className="inline-block w-1.5 h-4 bg-brand-500 align-text-bottom animate-pulse ml-0.5" />
            )}
            {message.isStreaming && !message.content && <StreamingDots />}
          </div>
        ) : null}

        {/* Diagrams */}
        {message.diagrams && message.diagrams.length > 0 && (
          <div className="mt-4 space-y-3">
            {message.diagrams.map((d, i) => (
              <DiagramCard key={i} diagram={d} index={i} />
            ))}
          </div>
        )}

        {/* Sources (collapsible) */}
        {message.sources && message.sources.length > 0 && (
          <div className="mt-4 border-t border-gray-100 pt-3">
            <button
              onClick={() => setShowSources((v) => !v)}
              className="text-xs font-medium text-gray-500 hover:text-gray-700 flex items-center gap-1"
            >
              <span>{showSources ? "▼" : "▶"}</span>
              {message.sources.length} source{message.sources.length === 1 ? "" : "s"}
            </button>
            {showSources && (
              <div className="mt-2 space-y-2">
                {message.sources.map((s, i) => (
                  <SourceCard key={s.chunk_id} source={s} index={i} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
