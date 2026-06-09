"use client";

/**
 * SourceCard — one citation from a chunk the retriever found.
 * Used in the collapsible "Sources" section of an AI message.
 */

import type { SourcePayload } from "@/lib/types";

export function SourceCard({ source, index }: { source: SourcePayload; index: number }) {
  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 text-sm">
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span className="font-mono bg-white border border-gray-200 px-1.5 py-0.5 rounded">
          {index + 1}
        </span>
        <span className="font-medium text-gray-700">{source.chapter_key}</span>
        {source.page != null && (
          <span>p. {source.page}</span>
        )}
        <span className="ml-auto text-gray-400">score {source.score.toFixed(3)}</span>
      </div>
      <p className="mt-1.5 text-gray-700 line-clamp-3">{source.preview}</p>
    </div>
  );
}
