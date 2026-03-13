/**
 * Shared types for the Nexo Partner SDK.
 * Aligned with backend schemas (backend/app/schemas.py).
 */

/** Webhook request payload. */
export interface WebhookPayload {
  event: "message_received";
  app: { id: string; name: string };
  thread: { id: string; customer_id: string | null };
  message: {
    id: string;
    seq: number;
    role: string;
    content: string;
    content_json: Record<string, unknown>;
  };
  history_tail: Array<{
    role: string;
    content: string;
    content_json: Record<string, unknown>;
  }>;
  tools?: Array<{ name: string; enabled: boolean }> | null;
  attachments?: Array<{ media_id: string; type: string; url: string }> | null;
  metadata?: Record<string, unknown>;
  timestamp: string;
}

export interface WebhookContentPart {
  type: string;
  text?: string;
  [key: string]: unknown;
}

/** Webhook response envelope. */
export interface WebhookResponse {
  schema_version: string;
  status: "completed" | "error";
  content_parts?: WebhookContentPart[];
  cards?: Array<Record<string, unknown>>;
  actions?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
  locale?: string;
  extensions?: Record<string, unknown>;
}

/** A thread as returned by the Partner API. */
export interface Thread {
  id: string;
  app_id: string;
  subscriber_id: string | null;
  title: string | null;
  status: "active" | "archived" | "deleted";
  customer_id: string | null;
  created_at: string;
  updated_at: string;
}

/** A message as returned by the Partner API. */
export interface Message {
  id: string;
  thread_id: string;
  seq: number;
  role: "user" | "assistant" | "system" | "tool";
  content: string | null;
  content_json: Record<string, unknown>;
  created_at: string;
}

/** Response from sending a proactive message. */
export interface MessageResponse {
  id: string;
  thread_id: string;
  seq: number;
  role: string;
  content: string | null;
  content_json: Record<string, unknown>;
  created_at: string;
}

/** A subscriber as returned by the Partner API. */
export interface Subscriber {
  id: string;
  app_id: string;
  customer_id: string;
  display_name: string | null;
  created_at: string;
  last_seen_at: string | null;
  last_message_at: string | null;
}

/** Options for constructing a NexoClient. */
export interface NexoClientOptions {
  apiKey: string;
  baseUrl: string;
}

/** Structured API error detail. */
export interface NexoErrorDetail {
  status: number;
  statusText: string;
  body: unknown;
}
