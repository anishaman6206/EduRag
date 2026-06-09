"use client";

/**
 * DiagramCard — renders one diagram from a textbook. If the
 * ingestion pipeline uploaded the image to Supabase Storage, the
 * `url` is a public URL. Otherwise it's empty and we show a
 * placeholder so the student knows the diagram exists.
 */

import type { DiagramPayload } from "@/lib/types";

export function DiagramCard({ diagram, index }: { diagram: DiagramPayload; index: number }) {
  return (
    <figure className="my-3 border border-gray-200 rounded-xl overflow-hidden bg-white">
      {diagram.url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={diagram.url}
          alt={diagram.caption || `Figure ${index + 1}`}
          className="w-full h-auto"
        />
      ) : (
        <div className="aspect-video flex flex-col items-center justify-center bg-gray-50 text-gray-400 text-sm p-6 text-center">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="9" cy="9" r="2" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
          <span className="mt-2 font-medium">Diagram not yet uploaded</span>
          <span className="text-xs text-gray-500 mt-1">
            The diagram exists in the textbook but its image isn't in storage yet.
          </span>
        </div>
      )}
      <figcaption className="px-4 py-2 text-xs text-gray-600 border-t border-gray-100 bg-gray-50">
        {diagram.caption || `Figure ${index + 1}`}
        {diagram.page != null && <span className="ml-2 text-gray-400">(page {diagram.page})</span>}
      </figcaption>
    </figure>
  );
}
