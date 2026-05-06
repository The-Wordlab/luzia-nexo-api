import type { PartnerWebhookPayload } from "./webhook-types";

export interface AgentHistoryEntry {
  role: string;
  content: string;
}

export interface BaseAgentSessionContext {
  currentMessage: string;
  displayName: string | null;
  locale: string | null;
  historyTail: AgentHistoryEntry[];
  messageContext: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  profile: Record<string, unknown> | null;
}

export interface BuildBaseAgentSessionContextOptions {
  historyLimit?: number;
}

export interface BuildBaseAgentConversationPromptOptions {
  title?: string;
  extraLines?: string[];
  currentMessageLabel?: string;
  historyLabel?: string;
}

export function getAgentStringValue(
  source: Record<string, unknown> | null | undefined,
  key: string,
): string | null {
  const value = source?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function getAgentObjectValue(
  source: Record<string, unknown> | null | undefined,
  key: string,
): Record<string, unknown> | null {
  const value = source?.[key];
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

export function getAgentStringArrayValue(
  source: Record<string, unknown> | null | undefined,
  key: string,
  limit = 5,
): string[] {
  const value = source?.[key];
  if (!Array.isArray(value)) {
    return [];
  }

  const normalized = value
    .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
    .filter(Boolean);

  return [...new Set(normalized)].slice(0, limit);
}

export function buildBaseAgentSessionContext(
  payload: PartnerWebhookPayload,
  options: BuildBaseAgentSessionContextOptions = {},
): BaseAgentSessionContext {
  const messageContext = payload.message.content_json ?? null;
  const metadata = payload.metadata ?? null;
  const profile = payload.profile ?? null;
  const historyLimit = options.historyLimit ?? 6;
  const locale =
    getAgentStringValue(payload as unknown as Record<string, unknown>, "locale") ||
    getAgentStringValue(profile ?? null, "locale") ||
    getAgentStringValue(metadata, "locale");

  return {
    currentMessage: payload.message.content.trim(),
    displayName:
      getAgentStringValue(profile ?? null, "display_name") ||
      getAgentStringValue(profile ?? null, "name"),
    locale,
    historyTail: payload.history_tail
      .slice(-historyLimit)
      .map((entry) => ({
        role: entry.role,
        content: entry.content,
      }))
      .filter((entry) => entry.content.trim()),
    messageContext:
      messageContext && typeof messageContext === "object" && !Array.isArray(messageContext)
        ? (messageContext as Record<string, unknown>)
        : null,
    metadata:
      metadata && typeof metadata === "object" && !Array.isArray(metadata)
        ? (metadata as Record<string, unknown>)
        : null,
    profile:
      profile && typeof profile === "object" && !Array.isArray(profile)
        ? (profile as Record<string, unknown>)
        : null,
  };
}

export function buildBaseAgentConversationPrompt(
  context: BaseAgentSessionContext,
  options: BuildBaseAgentConversationPromptOptions = {},
): string {
  const lines = [
    options.title ?? "Conversation context:",
    context.displayName ? `- User: ${context.displayName}` : "- User: anonymous",
    context.locale ? `- Locale: ${context.locale}` : "- Locale: unknown",
    ...(options.extraLines ?? []),
  ];

  if (context.historyTail.length > 0) {
    lines.push(options.historyLabel ?? "- Recent history:");
    for (const entry of context.historyTail) {
      lines.push(`  - ${entry.role}: ${entry.content}`);
    }
  }

  lines.push(options.currentMessageLabel ?? "- Current user message:");
  lines.push(context.currentMessage);
  return lines.join("\n");
}
