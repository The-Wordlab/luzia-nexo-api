/**
 * Webhook response envelope builders.
 *
 * Builds the standard Nexo partner response format with task metadata,
 * content parts, cards, and error details.
 */

import { randomUUID } from "crypto";
import type {
  PartnerContentPart,
  PartnerWebhookError,
  PartnerWebhookResponse,
} from "./webhook-types";

export const PARTNER_SCHEMA_VERSION = "2026-03";

export interface SuccessEnvelopeInput {
  text: string;
  taskId?: string;
  taskMessage?: string;
  cards?: Array<Record<string, unknown>>;
  actions?: Array<Record<string, unknown>>;
  artifacts?: Array<Record<string, unknown>>;
  capabilityName?: string;
  metadata?: Record<string, unknown>;
  locale?: string;
}

export interface FailureEnvelopeInput {
  userMessage: string;
  error: PartnerWebhookError;
  taskId?: string;
  capabilityName?: string;
  metadata?: Record<string, unknown>;
  locale?: string;
}

function withTextContent(
  text: string,
  existing: PartnerContentPart[] | undefined,
): PartnerContentPart[] | undefined {
  if (!text) return existing;
  const parts = existing ? [...existing] : [];
  if (!parts.some((p) => p.type === "text" && typeof p.text === "string")) {
    parts.unshift({ type: "text", text });
  }
  return parts;
}

export function buildSuccessEnvelope(input: SuccessEnvelopeInput): PartnerWebhookResponse {
  const envelope: PartnerWebhookResponse = {
    schema_version: PARTNER_SCHEMA_VERSION,
    task: {
      id: input.taskId || randomUUID(),
      status: "completed",
      can_retry: false,
      can_cancel: false,
      message: input.taskMessage || "completed",
    },
    content_parts: withTextContent(input.text, []),
  };

  if (input.cards?.length) envelope.cards = input.cards;
  if (input.actions?.length) envelope.actions = input.actions;
  if (input.artifacts?.length) envelope.artifacts = input.artifacts;
  if (input.capabilityName) envelope.capability = { name: input.capabilityName, version: "1" };
  if (input.metadata && Object.keys(input.metadata).length > 0) envelope.metadata = input.metadata;
  if (input.locale) envelope.locale = input.locale;

  return envelope;
}

export function buildFailureEnvelope(input: FailureEnvelopeInput): PartnerWebhookResponse {
  const envelope: PartnerWebhookResponse = {
    schema_version: PARTNER_SCHEMA_VERSION,
    task: {
      id: input.taskId || randomUUID(),
      status: "failed",
      can_retry: input.error.retryable,
      can_cancel: false,
      message: input.userMessage,
    },
    error: input.error,
    content_parts: withTextContent(input.userMessage, []),
  };

  if (input.capabilityName) envelope.capability = { name: input.capabilityName, version: "1" };
  if (input.metadata && Object.keys(input.metadata).length > 0) envelope.metadata = input.metadata;
  if (input.locale) envelope.locale = input.locale;

  return envelope;
}

export function withStreamText(
  envelope: PartnerWebhookResponse,
  text: string,
): PartnerWebhookResponse {
  return {
    ...envelope,
    text,
    content_parts: withTextContent(text, envelope.content_parts),
  };
}
