"use client";

/**
 * Three animated dots — shown next to a message while the AI is
 * still streaming. Pure CSS animation, no JS.
 */

export function StreamingDots() {
  return (
    <span className="inline-flex gap-0.5 ml-1 align-baseline" aria-label="Streaming">
      <span className="h-1.5 w-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="h-1.5 w-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="h-1.5 w-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
    </span>
  );
}
