/**
 * Content block rendering registry.
 *
 * The SDK owns the dispatch mechanism and built-in renderers for generic
 * block types (text, image, webview, video). Apps register custom renderers
 * for domain-specific `data` block formats (e.g., nutrition.daily_summary).
 *
 * See docs/specs/message-content-contract.md for the full spec.
 */

import type { ContentBlock } from "./chat-types";

/**
 * A block renderer receives the block data and returns a React element
 * (or null to skip rendering).
 */
export type BlockRenderer = (block: ContentBlock) => React.ReactElement | null;

/** Registry of format-specific renderers for `data` blocks. */
const formatRenderers = new Map<string, BlockRenderer>();

/**
 * Register a renderer for a specific data block format.
 *
 * Call this at app init time to teach the SDK how to render your
 * domain-specific block formats.
 *
 * @example
 * registerBlockRenderer("nutrition.daily_summary", (block) => (
 *   <NutritionSummaryCard data={block.data} />
 * ));
 */
export function registerBlockRenderer(format: string, renderer: BlockRenderer): void {
  formatRenderers.set(format, renderer);
}

/**
 * Look up a registered renderer for a data block format.
 * Returns undefined if no renderer is registered.
 */
export function getBlockRenderer(format: string): BlockRenderer | undefined {
  return formatRenderers.get(format);
}

/**
 * Clear all registered renderers. Useful for tests.
 */
export function clearBlockRenderers(): void {
  formatRenderers.clear();
}
