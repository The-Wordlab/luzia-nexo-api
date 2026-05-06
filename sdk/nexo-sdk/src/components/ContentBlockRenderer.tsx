/**
 * Renders an ordered list of content blocks.
 *
 * Dispatches each block by type:
 * - text: renders as a paragraph
 * - data: looks up a registered format renderer, falls back to hidden
 * - image: renders an img tag
 * - video: renders a video tag
 * - webview: renders an iframe
 * - unknown: silently ignored (safe fallback per PRD)
 */

import type { ContentBlock } from "../chat-types";
import { getBlockRenderer } from "../content-blocks";

export interface ContentBlockRendererProps {
  blocks: ContentBlock[];
  /** Plain text fallback shown when no blocks produce visible output. */
  fallbackText?: string;
  className?: string;
}

export function ContentBlockRenderer({ blocks, fallbackText, className }: ContentBlockRendererProps) {
  // Check if any block would render visible output
  const hasVisibleBlock = blocks.some((block) => {
    if (block.type === "text" && block.text) return true;
    if (block.type === "data" && block.format && getBlockRenderer(block.format)) return true;
    if ((block.type === "image" || block.type === "video" || block.type === "webview") && block.url) return true;
    return false;
  });

  // Fall back to plain text if no blocks would render
  if (!hasVisibleBlock && fallbackText) {
    return <>{fallbackText}</>;
  }

  return (
    <div className={`nexo-content-blocks ${className ?? ""}`}>
      {blocks.map((block, i) => (
        <ContentBlockItem key={i} block={block} />
      ))}
    </div>
  );
}

function ContentBlockItem({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case "text":
      return block.text ? <p className="nexo-content-block nexo-content-block--text">{block.text}</p> : null;

    case "data": {
      if (!block.format) return null;
      const renderer = getBlockRenderer(block.format);
      if (renderer) return renderer(block);
      // No registered renderer - skip silently (safe fallback)
      return null;
    }

    case "image":
      return block.url ? (
        <img
          className="nexo-content-block nexo-content-block--image"
          src={block.url}
          alt={block.alt ?? ""}
          width={block.width}
          height={block.height}
        />
      ) : null;

    case "video":
      return block.url ? (
        <video
          className="nexo-content-block nexo-content-block--video"
          src={block.url}
          controls
          width={block.width}
          height={block.height}
        />
      ) : null;

    case "webview":
      return block.url ? (
        <iframe
          className="nexo-content-block nexo-content-block--webview"
          src={block.url}
          title={block.alt ?? ""}
          width={block.width ?? "100%"}
          height={block.height ?? 300}
          style={{ border: "none" }}
        />
      ) : null;

    default:
      // Unknown block type - silently skip (forward compatibility)
      return null;
  }
}
