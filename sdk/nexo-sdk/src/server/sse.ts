/**
 * SSE streaming helpers for the partner webhook contract.
 *
 * Nexo partner inbound SSE contract:
 * - Bare `data:` lines for text chunks
 * - `event: done` with the full response envelope
 * - Optional `event: progress` for perceived-latency feedback
 */

import type { PartnerWebhookResponse } from "./webhook-types";
import { withStreamText } from "./envelope";

function formatSseData(data: string): string {
  return data
    .split(/\n/u)
    .map((line) => `data: ${line}`)
    .join("\n");
}

function chunkText(text: string, maxLength = 72): string[] {
  if (!text.trim()) return [];
  const chunks: string[] = [];
  let current = "";

  for (const word of text.split(/\s+/u)) {
    if (!word) continue;
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > maxLength && current) {
      chunks.push(current);
      current = word;
      continue;
    }
    current = candidate;
  }
  if (current) chunks.push(current);
  return chunks;
}

/** Check if the client wants SSE streaming. */
export function shouldStreamResponse(acceptHeader: string | undefined): boolean {
  return (acceptHeader || "").includes("text/event-stream");
}

/** Format a progress event for perceived-latency feedback during tool use. */
export function formatProgressEvent(message: string, stage?: string): string {
  const payload = JSON.stringify({
    kind: "progress",
    message,
    stage: stage || undefined,
  });
  return `event: progress\n${formatSseData(payload)}\n\n`;
}

/** Stream text response with typing simulation, then emit done envelope. */
export async function* streamTextResponse(
  text: string,
  envelope: PartnerWebhookResponse,
  chunkDelayMs = 50,
): AsyncGenerator<string> {
  const chunks = chunkText(text);
  for (let i = 0; i < chunks.length; i++) {
    yield `${formatSseData(chunks[i])}\n\n`;
    if (i < chunks.length - 1) {
      await new Promise((resolve) => setTimeout(resolve, chunkDelayMs));
    }
  }
  const doneEnvelope = withStreamText(envelope, text);
  yield `event: done\n${formatSseData(JSON.stringify(doneEnvelope))}\n\n`;
}
