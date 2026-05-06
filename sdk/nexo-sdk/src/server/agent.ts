import { runAgentLoop, type AgentLoopResult } from "./agent/loop";
import type { AgentTool } from "./agent/types";
import type { LLMClient, LLMMessage } from "./llm/types";
import type { PartnerWebhookPayload } from "./webhook-types";

export interface PartnerAgentCapability {
  name: string;
  description: string;
  supports_streaming: boolean;
  supports_cancellation: boolean;
  metadata?: Record<string, unknown>;
}

export interface PartnerAgentCard {
  name: string;
  description: string;
  url: string;
  version: string;
  capabilities: {
    items: PartnerAgentCapability[];
  };
}

export interface AgentTurnBuildContext<SessionContext> {
  payload: PartnerWebhookPayload;
  sessionContext: SessionContext;
  tools: AgentTool[];
}

export interface AgentTurnReplyContext<SessionContext>
  extends AgentTurnBuildContext<SessionContext> {
  systemPrompt: string;
  userPrompt: string;
  initialMessages: LLMMessage[];
  loopResult: AgentLoopResult;
}

export interface AgentDefinition<SessionContext, Reply> {
  buildSessionContext: (
    payload: PartnerWebhookPayload,
  ) => SessionContext | Promise<SessionContext>;
  buildTools: (
    context: AgentTurnBuildContext<SessionContext>,
  ) => AgentTool[] | Promise<AgentTool[]>;
  buildSystemPrompt: (
    context: AgentTurnBuildContext<SessionContext>,
  ) => string | Promise<string>;
  buildUserPrompt: (
    payload: PartnerWebhookPayload,
    sessionContext: SessionContext,
  ) => string | Promise<string>;
  buildInitialMessages?: (
    context: AgentTurnBuildContext<SessionContext>,
  ) => LLMMessage[] | Promise<LLMMessage[]>;
  buildReply: (
    context: AgentTurnReplyContext<SessionContext>,
  ) => Reply | Promise<Reply>;
}

export interface ExecuteAgentTurnOptions<SessionContext, Reply>
  extends AgentDefinition<SessionContext, Reply> {
  payload: PartnerWebhookPayload;
  client: LLMClient;
  maxTurns?: number;
}

export interface ExecuteAgentDefinitionOptions<SessionContext, Reply> {
  payload: PartnerWebhookPayload;
  client: LLMClient;
  definition: AgentDefinition<SessionContext, Reply>;
  maxTurns?: number;
}

export function defineAgent<SessionContext, Reply>(
  definition: AgentDefinition<SessionContext, Reply>,
): AgentDefinition<SessionContext, Reply> {
  return definition;
}

export async function executeAgentTurn<SessionContext, Reply>({
  payload,
  client,
  maxTurns,
  buildSessionContext,
  buildTools,
  buildSystemPrompt,
  buildUserPrompt,
  buildInitialMessages,
  buildReply,
}: ExecuteAgentTurnOptions<SessionContext, Reply>): Promise<Reply> {
  const sessionContext = await buildSessionContext(payload);
  const tools = await buildTools({ payload, sessionContext, tools: [] });
  const buildContext = { payload, sessionContext, tools };
  const [systemPrompt, userPrompt, initialMessages] = await Promise.all([
    buildSystemPrompt(buildContext),
    buildUserPrompt(payload, sessionContext),
    buildInitialMessages ? buildInitialMessages(buildContext) : [],
  ]);

  const loopResult = await runAgentLoop({
    client,
    systemPrompt,
    userPrompt,
    tools,
    initialMessages,
    maxTurns,
  });

  return await buildReply({
    ...buildContext,
    systemPrompt,
    userPrompt,
    initialMessages,
    loopResult,
  });
}

export async function executeAgentDefinition<SessionContext, Reply>({
  payload,
  client,
  definition,
  maxTurns,
}: ExecuteAgentDefinitionOptions<SessionContext, Reply>): Promise<Reply> {
  return executeAgentTurn({
    ...definition,
    payload,
    client,
    maxTurns,
  });
}
