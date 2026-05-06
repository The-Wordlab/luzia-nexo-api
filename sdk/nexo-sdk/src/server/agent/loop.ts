/**
 * Tool-calling agent loop.
 *
 * Runs a think-tool-answer cycle:
 * 1. Ask the LLM: use a tool or give a final answer?
 * 2. If tool: execute it, feed result back, repeat
 * 3. If final: return the answer
 *
 * Max turns prevent infinite loops. Tool failures are fed back
 * so the LLM can answer from its own knowledge instead.
 */

import type { LLMClient, LLMMessage } from "../llm/types";
import type { AgentTool } from "./types";

interface ToolDecision {
  kind: "tool";
  tool: string;
  args: Record<string, unknown>;
  reason?: string;
}

interface FinalDecision {
  kind: "final";
  answer: string;
  follow_up_questions?: string[];
}

type AgentDecision = ToolDecision | FinalDecision;

export interface AgentLoopInput {
  client: LLMClient;
  systemPrompt: string;
  userPrompt: string;
  tools: AgentTool[];
  initialMessages?: LLMMessage[];
  maxTurns?: number;
}

export interface AgentLoopResult {
  answer: string;
  followUpQuestions: string[];
  toolsUsed: string[];
  toolResults: Record<string, unknown>;
}

function stripCodeFences(text: string): string {
  return text
    .trim()
    .replace(/^```json\s*/u, "")
    .replace(/^```\s*/u, "")
    .replace(/\s*```$/u, "")
    .trim();
}

function parseDecision(raw: string): AgentDecision {
  const cleaned = stripCodeFences(raw);
  try {
    const parsed = JSON.parse(cleaned) as Partial<AgentDecision>;
    if (parsed.kind === "tool" && typeof parsed.tool === "string") {
      return {
        kind: "tool",
        tool: parsed.tool,
        args:
          parsed.args && typeof parsed.args === "object" && !Array.isArray(parsed.args)
            ? (parsed.args as Record<string, unknown>)
            : {},
        reason: typeof parsed.reason === "string" ? parsed.reason : undefined,
      };
    }
    if (parsed.kind === "final" && typeof parsed.answer === "string") {
      return {
        kind: "final",
        answer: parsed.answer,
        follow_up_questions: Array.isArray(parsed.follow_up_questions)
          ? parsed.follow_up_questions.filter(
              (v): v is string => typeof v === "string" && v.trim().length > 0,
            )
          : [],
      };
    }
  } catch {
    // LLM returned non-JSON - treat as final answer
  }

  return { kind: "final", answer: cleaned, follow_up_questions: [] };
}

export async function runAgentLoop({
  client,
  systemPrompt,
  userPrompt,
  tools,
  initialMessages = [],
  maxTurns = 4,
}: AgentLoopInput): Promise<AgentLoopResult> {
  const toolMap = new Map(tools.map((t) => [t.name, t]));
  const toolResults: Record<string, unknown> = {};
  const toolsUsed: string[] = [];
  const messages: LLMMessage[] = [
    { role: "system", content: systemPrompt },
    ...initialMessages,
    { role: "user", content: userPrompt },
  ];

  for (let turn = 0; turn < maxTurns; turn += 1) {
    const raw = await client.generate(messages, {
      responseMimeType: "application/json",
      temperature: 0.2,
    });
    const decision = parseDecision(raw);
    messages.push({ role: "assistant", content: raw });

    if (decision.kind === "final") {
      return {
        answer: decision.answer.trim(),
        followUpQuestions: (decision.follow_up_questions ?? []).slice(0, 3),
        toolsUsed,
        toolResults,
      };
    }

    const tool = toolMap.get(decision.tool);
    if (!tool) {
      messages.push({
        role: "tool",
        name: decision.tool,
        content: JSON.stringify({
          error: `Unknown tool: ${decision.tool}. Available: ${Array.from(toolMap.keys()).join(", ")}`,
        }),
      });
      continue;
    }

    try {
      const result = await tool.execute(decision.args);
      toolResults[tool.name] = result;
      toolsUsed.push(tool.name);
      messages.push({ role: "tool", name: tool.name, content: JSON.stringify(result) });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toolsUsed.push(tool.name);
      messages.push({
        role: "tool",
        name: tool.name,
        content: JSON.stringify({
          error: msg,
          hint: "This tool failed. Answer from your own knowledge instead.",
        }),
      });
    }
  }

  throw new Error("Agent loop exceeded maximum turns");
}
