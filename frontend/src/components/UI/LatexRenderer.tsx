"use client";

/**
 * LatexRenderer — wraps react-katex so we can pass LaTeX strings
 * from the LLM and render them as math.
 *
 * Used for individual formulas. For the whole message body (which
 * mixes prose + math) we use react-markdown with remark-math +
 * rehype-katex, configured in MessageBubble.
 */

import { InlineMath, BlockMath } from "react-katex";
import "katex/dist/katex.min.css";

interface Props {
  math: string;
  block?: boolean;
}

export function LatexRenderer({ math, block = false }: Props) {
  try {
    if (block) return <BlockMath math={math} />;
    return <InlineMath math={math} />;
  } catch (e) {
    // KaTeX threw on the input (probably not real LaTeX). Fall back
    // to plain text so the message still renders.
    return <code className="text-red-600">{math}</code>;
  }
}
