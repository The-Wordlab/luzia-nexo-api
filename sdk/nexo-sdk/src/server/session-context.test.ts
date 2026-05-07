import { describe, expect, it } from "vitest";
import type { PartnerWebhookPayload } from "./webhook-types";
import {
  buildBaseAgentConversationPrompt,
  buildBaseAgentSessionContext,
  getAgentStringArrayValue,
} from "./session-context";

function createPayload(
  overrides: Partial<PartnerWebhookPayload> = {},
): PartnerWebhookPayload {
  return {
    message: {
      messageId: "msg-1",
      contextId: "thread-1",
      role: "user",
      parts: [{ type: "text", text: "How does this look?" }],
      metadata: {
        app: { id: "app-1", name: "WC2026 Predictor" },
        thread: { id: "thread-1", customer_id: null },
        profile: { display_name: "Mark" },
        locale: "es",
        history_tail: [
          { role: "user", content: "Earlier question" },
          { role: "assistant", content: "Earlier answer" },
        ],
        timestamp: "2026-04-25T12:00:00Z",
        group_id: "group-a",
      },
    },
    ...overrides,
  };
}

describe("session-context SDK helpers", () => {
  it("builds a reusable base session context from webhook payloads", () => {
    const context = buildBaseAgentSessionContext(createPayload());

    expect(context.currentMessage).toBe("How does this look?");
    expect(context.displayName).toBe("Mark");
    expect(context.locale).toBe("es");
    expect(context.messageContext).toBeNull();
    expect(context.metadata).toMatchObject({ locale: "es", group_id: "group-a" });
    expect(context.historyTail).toEqual([
      { role: "user", content: "Earlier question" },
      { role: "assistant", content: "Earlier answer" },
    ]);
  });

  it("normalizes unique string arrays from context objects", () => {
    const values = getAgentStringArrayValue(
      {
        favorite_teams: [" Mexico ", "", "South Africa", "Mexico"],
      },
      "favorite_teams",
    );

    expect(values).toEqual(["Mexico", "South Africa"]);
  });

  it("builds a generic conversation prompt scaffold", () => {
    const prompt = buildBaseAgentConversationPrompt(
      buildBaseAgentSessionContext(createPayload()),
      {
        title: "World Cup conversation context:",
        extraLines: ["- Selected match hint: match-001"],
      },
    );

    expect(prompt).toContain("World Cup conversation context:");
    expect(prompt).toContain("- User: Mark");
    expect(prompt).toContain("- Locale: es");
    expect(prompt).toContain("- Selected match hint: match-001");
    expect(prompt).toContain("- Recent history:");
    expect(prompt).toContain("- Current user message:");
  });
});
