"use client";

/**
 * MermaidBlock — renders a ```mermaid code block as SVG.
 *
 * Mermaid is initialized once (lazily) on the client. Each block
 * is given a unique id so multiple diagrams on the same page don't
 * collide. If the diagram fails to parse, we fall back to showing
 * the raw code in a styled <pre> so the user still sees the
 * intent.
 */

import { useEffect, useRef, useState } from "react";

let mermaidInitialized = false;
let mermaidModule: typeof import("mermaid") | null = null;

async function getMermaid() {
  if (mermaidInitialized && mermaidModule) return mermaidModule;
  const m = await import("mermaid");
  m.default.initialize({
    startOnLoad: false,
    theme: "default",
    securityLevel: "loose",
    fontFamily: "system-ui, sans-serif",
  });
  mermaidModule = m;
  mermaidInitialized = true;
  return m;
}

interface Props {
  code: string;
  id?: string;
}

export function MermaidBlock({ code, id }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [svg, setSvg] = useState<string>("");
  const blockId = id || `mermaid-${Math.random().toString(36).slice(2, 10)}`;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await getMermaid();
        if (cancelled || !ref.current) return;
        // mermaid.render returns { svg } in v10+
        const result = await m.default.render(blockId, code);
        if (cancelled) return;
        setSvg(result.svg);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, blockId]);

  if (error) {
    return (
      <div className="my-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
        <div className="text-xs font-semibold text-amber-800 mb-1">
          Diagram (could not render):
        </div>
        <pre className="text-xs text-amber-900 overflow-x-auto whitespace-pre-wrap">
          {code}
        </pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="my-3 flex items-center justify-center py-8 bg-gray-50 rounded-lg border border-gray-200">
        <span className="text-xs text-gray-400">Rendering diagram…</span>
      </div>
    );
  }

  return (
    <div
      ref={ref}
      className="my-3 flex justify-center bg-white rounded-lg border border-gray-200 p-3 overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
