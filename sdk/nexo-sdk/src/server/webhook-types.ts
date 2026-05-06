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

export interface PartnerWebhookPayload {
  event: "message_received";
  app: { id: string; name: string };
  thread: { id: string; customer_id: string | null };
  message: {
    id: string;
    seq: number;
    role: string;
    content: string;
    content_json?: Record<string, unknown> | null;
  };
  history_tail: Array<{
    role: string;
    content: string;
    content_json?: Record<string, unknown> | null;
  }>;
  tools?: Array<{ name: string; enabled: boolean }> | null;
  attachments?: Array<{ media_id: string; type: string; url: string }> | null;
  metadata?: Record<string, unknown> | null;
  profile?: PartnerProfile | null;
  locale_source?: string | null;
  timestamp: string;
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
