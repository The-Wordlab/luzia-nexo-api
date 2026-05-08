/**
 * @luzia/nexo-sdk server-side modules.
 *
 * Node-only. For Express-based agent apps.
 * Import from "@luzia/nexo-sdk/server".
 */

// Webhook signing and verification
export { signRequest, verifyWebhookSignature } from "./signature";
export type { VerifySignatureOptions } from "./signature";

export { buildSuccessEnvelope, buildFailureEnvelope, withStreamText, PARTNER_SCHEMA_VERSION } from "./envelope";
export type { SuccessEnvelopeInput, FailureEnvelopeInput } from "./envelope";

export { shouldStreamResponse, formatProgressEvent, streamTextResponse } from "./sse";

// Auth bridge
export { createNexoAuthRouter } from "./auth-bridge";
export type { NexoAuthBridgeConfig } from "./auth-bridge";

// LLM
export { createGeminiClient } from "./llm/gemini";
export {
  buildGoogleGenAIOptions,
  buildGeminiGenerateRequest,
  GeminiLLMClient,
} from "./llm/gemini";
export type { GeminiClientOptions, GeminiAuthMode } from "./llm/gemini";
export type { LLMClient, LLMMessage, LLMRole, LLMGenerateOptions } from "./llm/types";

// Agent session context
export {
  buildBaseAgentSessionContext,
  buildBaseAgentConversationPrompt,
  getAgentStringValue,
  getAgentObjectValue,
  getAgentStringArrayValue,
} from "./session-context";
export type {
  BaseAgentSessionContext,
  AgentHistoryEntry,
  BuildBaseAgentSessionContextOptions,
  BuildBaseAgentConversationPromptOptions,
} from "./session-context";

// Agent loop
export { runAgentLoop } from "./agent/loop";
export type { AgentLoopInput, AgentLoopResult } from "./agent/loop";
export type { AgentTool } from "./agent/types";
export {
  defineAgent,
  executeAgentTurn,
  executeAgentDefinition,
} from "./agent";
export type {
  AgentDefinition,
  ExecuteAgentTurnOptions,
  ExecuteAgentDefinitionOptions,
  AgentTurnBuildContext,
  AgentTurnReplyContext,
  PartnerAgentCapability,
  PartnerAgentCard,
} from "./agent";

// Nexo server client
export { NexoServerClient, NexoRequestError } from "./nexo-client";
export type {
  NexoServerClientConfig,
  NexoNativeSessionExchangeInput,
  NexoNativeSessionExchangeResponse,
  KPRecord,
  KnowledgePack,
  KnowledgePackDataset,
  App,
  AppParticipant,
  AppTable,
  NexoProfile,
  DemoPersona,
  TableQueryFilter,
  TableQueryBody,
  TableRecord,
  TableQueryResponse,
  TableRecordCreateBody,
  TableRecordUpdateBody,
} from "./nexo-client";

// Types
export { extractTextFromPayload } from "./webhook-types";
export type {
  PartnerWebhookPayload,
  PartnerWebhookResponse,
  PartnerWebhookError,
  PartnerContentPart,
  PartnerTask,
  PartnerProfile,
} from "./webhook-types";
