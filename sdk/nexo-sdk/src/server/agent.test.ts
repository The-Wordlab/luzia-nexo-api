import { describe, expect, it } from "vitest";
import { executeAgentTurn } from "./agent";
import type { LLMClient, LLMMessage } from "./llm/types";

class FakeLLMClient implements LLMClient {
  readonly model = "fake/test-model";
  private index = 0;

  constructor(private readonly responses: string[]) {}

  async generate(): Promise<string> {
    const response = this.responses[this.index];
    this.index += 1;
    if (!response) {
      throw new Error("No more fake LLM responses configured");
    }
    return response;
  }
}

describe("executeAgentTurn", () => {
  it("runs the generic agent orchestration and delegates reply shaping", async () => {
    const client = new FakeLLMClient([
      JSON.stringify({
        kind: "tool",
        tool: "lookup_fixture",
        args: { fixture_id: "match-001" },
      }),
      JSON.stringify({
        kind: "final",
        answer: "Mexico look slightly stronger, but it should stay tight.",
        follow_up_questions: ["How risky is a draw?"],
      }),
    ]);

    const payload = {
      message: {
        messageId: "msg-1",
        contextId: "thread-1",
        role: "user",
        parts: [{ type: "text", text: "How do you see Mexico vs South Africa?" }],
        metadata: {
          app: { id: "app-1", name: "Example App" },
          thread: { id: "thread-1" },
          locale: "en",
          history_tail: [],
          timestamp: "2026-05-02T18:00:00Z",
        },
      },
    } as const;

    const reply = await executeAgentTurn({
      payload,
      client,
      buildSessionContext: (incoming) => ({
        locale: "en",
        currentMessage: incoming.message.parts[0].text ?? "",
      }),
      buildTools: () => [
        {
          name: "lookup_fixture",
          description: "load one fixture",
          inputSchema: '{"fixture_id":"string"}',
          execute: async () => ({
            fixture: { id: "match-001", label: "Mexico vs South Africa" },
          }),
        },
      ],
      buildSystemPrompt: () => "Answer like a concise pundit.",
      buildUserPrompt: (_incoming, sessionContext) => sessionContext.currentMessage,
      buildInitialMessages: async () =>
        [{ role: "system", content: "unused bootstrap" }] satisfies LLMMessage[],
      buildReply: ({ sessionContext, initialMessages, loopResult }) => ({
        locale: sessionContext.locale,
        initialMessageCount: initialMessages.length,
        answer: loopResult.answer,
        followUp: loopResult.followUpQuestions,
        toolsUsed: loopResult.toolsUsed,
        fixture: loopResult.toolResults.lookup_fixture,
      }),
    });

    expect(reply).toEqual({
      locale: "en",
      initialMessageCount: 1,
      answer: "Mexico look slightly stronger, but it should stay tight.",
      followUp: ["How risky is a draw?"],
      toolsUsed: ["lookup_fixture"],
      fixture: {
        fixture: { id: "match-001", label: "Mexico vs South Africa" },
      },
    });
  });
});
