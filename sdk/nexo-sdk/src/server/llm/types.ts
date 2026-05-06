/**
 * Provider-agnostic LLM client interface.
 *
 * Agent apps implement this to call any LLM (Gemini, Claude, OpenAI).
 * The agent loop uses this interface - it doesn't know which provider is behind it.
 */

export type LLMRole = "system" | "user" | "assistant" | "tool";

export interface LLMMessage {
  role: LLMRole;
  content: string;
  name?: string;
}

export interface LLMGenerateOptions {
  temperature?: number;
  responseMimeType?: "application/json" | "text/plain";
}

export interface LLMClient {
  readonly model: string;
  generate(messages: LLMMessage[], options?: LLMGenerateOptions): Promise<string>;
}
