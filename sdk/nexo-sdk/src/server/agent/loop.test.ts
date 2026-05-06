import { describe, expect, it } from "vitest";
import { runAgentLoop } from "./loop";
import type { AgentTool } from "./types";
import type { LLMClient } from "../llm/types";

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

describe("runAgentLoop", () => {
  it("executes a tool call before returning the final answer", async () => {
    const client = new FakeLLMClient([
      JSON.stringify({
        kind: "tool",
        tool: "get_match_context",
        args: { match_id: "match-001" },
      }),
      JSON.stringify({
        kind: "final",
        answer: "Mexico should shade it, but South Africa can make this messy.",
        follow_up_questions: [
          "What does Group A look like?",
          "Who are the key Mexico players?",
        ],
      }),
    ]);

    const tools: AgentTool[] = [
      {
        name: "get_match_context",
        description: "load match context",
        inputSchema: '{"match_id":"string"}',
        execute: async () => ({
          match: { id: "match-001", label: "Mexico vs South Africa" },
        }),
      },
    ];

    const result = await runAgentLoop({
      client,
      systemPrompt: "test system",
      userPrompt: "Tell me about Mexico vs South Africa",
      tools,
    });

    expect(result.answer).toContain("Mexico should shade it");
    expect(result.followUpQuestions).toEqual([
      "What does Group A look like?",
      "Who are the key Mexico players?",
    ]);
    expect(result.toolsUsed).toEqual(["get_match_context"]);
    expect(result.toolResults.get_match_context).toEqual({
      match: { id: "match-001", label: "Mexico vs South Africa" },
    });
  });
});
