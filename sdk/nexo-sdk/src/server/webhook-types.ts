/**
 * Nexo partner webhook contract types.
 *
 * These define the inbound payload from Nexo and the outbound response
 * envelope. Stable across all agent apps.
 */

export interface PartnerProfile {
  display_name?: string | null;
  name?: string | null;
  locale?: string | null;
  [key: string]: unknown;
}

/**
 * A2A Message-shaped webhook payload from Nexo.
 *
 * Nexo sends this shape. Text is in message.parts[0].text,
 * profile/locale/history are in message.metadata.
 */
export interface PartnerWebhookPayload {
  message: {
    messageId: string;
    contextId?: string;
    role: string;
    parts: Array<{ type: string; text?: string; data?: unknown }>;
    metadata?: {
      app?: { id: string; name: string };
      thread?: { id: string; customer_id?: string | null };
      profile?: PartnerProfile | null;
      locale?: string | null;
      locale_source?: string | null;
      history_tail?: Array<{
        role: string;
        content: string;
        content_json?: Record<string, unknown> | null;
      }>;
      timestamp?: string;
      [key: string]: unknown;
    } | null;
    [key: string]: unknown;
  };
  configuration?: Record<string, unknown> | null;
}

/** Helper: extract text from an A2A message parts array. */
export function extractTextFromPayload(payload: PartnerWebhookPayload): string {
  const parts = payload.message?.parts;
  if (Array.isArray(parts)) {
    const textPart = parts.find((p) => p.type === "text" && typeof p.text === "string");
    if (textPart?.text) return textPart.text;
  }
  return "";
}

export interface PartnerContentPart {
  type: string;
  text?: string;
  [key: string]: unknown;
}

export interface PartnerTask {
  id: string;
  status: "completed" | "failed";
  can_retry?: boolean;
  can_cancel?: boolean;
  message?: string;
}

export interface PartnerWebhookError {
  code: string;
  message: string;
  retryable: boolean;
  retry_after_ms?: number;
  details?: Record<string, unknown>;
}

export interface PartnerWebhookResponse {
  schema_version: string;
  task: PartnerTask;
  content_parts?: PartnerContentPart[];
  cards?: Array<Record<string, unknown>>;
  actions?: Array<Record<string, unknown>>;
  artifacts?: Array<Record<string, unknown>>;
  capability?: { name: string; version: string };
  error?: PartnerWebhookError | null;
  metadata?: Record<string, unknown>;
  locale?: string;
  extensions?: Record<string, unknown>;
  text?: string;
}
