/**
 * remarkMermaid — a tiny remark plugin that detects ```mermaid code
 * blocks in markdown and converts them to a custom node so we can
 * render them with the MermaidBlock component (which uses the
 * mermaid library to compile them client-side to SVG).
 *
 * Without this, react-markdown would render the mermaid code as
 * a plain <pre><code> block, which isn't useful.
 *
 * The node shape we attach:
 *   { type: 'html', value: '<!--MERMAID:...-->', data: { hName: 'MermaidBlock', hProperties: { code: '...' } } }
 *
 * react-markdown supports this via the `components` prop, which we
 * use in MessageBubble to swap <MermaidBlock> in for these nodes.
 */

/**
 * remarkMermaid — converts ```mermaid code blocks into placeholder
 * paragraphs with a `data-mermaid-code` attribute. MessageBubble
 * then walks the rendered React tree to find these and swap them
 * out for MermaidBlock components (avoids fighting react-markdown's
 * components-prop typing, which only allows HTML element names).
 *
 * The placeholder is a paragraph with one text child (the raw
 * mermaid source). The components-map handles any element name,
 * so we use a custom HTML element <div data-mermaid-code="...">
 * and override div rendering in MessageBubble.
 */

import { SKIP, visit } from "unist-util-visit";
import type { Plugin } from "unified";
import type { Root, Code, Paragraph, Text } from "mdast";

export const remarkMermaid: Plugin<[], Root> = function () {
  return (tree) => {
    visit(tree, "code", (node: Code, index, parent) => {
      if (!parent || typeof index !== "number") return;
      if (node.lang !== "mermaid") return;

      // Replace the code node with a paragraph whose only text child
      // is a marker. The components map in MessageBubble intercepts
      // paragraphs whose only text child starts with this marker and
      // renders MermaidBlock instead.
      const text: Text = {
        type: "text",
        value: `__MERMAID_BLOCK__${node.value}__END__`,
      } as Text;
      const para: Paragraph = {
        type: "paragraph",
        children: [text],
      } as Paragraph;
      parent.children.splice(index, 1, para);
      return [SKIP, index + 1] as any;
    });
  };
};

