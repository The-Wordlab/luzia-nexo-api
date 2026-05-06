/**
 * Types for the Nexo chat/personality system.
 *
 * These mirror the backend PersonalityPublicRead and agent SSE contracts.
 * Components are controlled - the host provides personality data, not the SDK.
 */

/** A Nexo personality linked to an app. */
export interface Personality {
  id: string;
  slug: string;
  name: string;
  description?: string;
  greeting: string;
  suggestions: string[];
  assets: PersonalityAssets;
  brand: PersonalityBrand;
}

export interface PersonalityAssets {
  avatarLight?: string;
  avatarDark?: string;
  avatarSmall?: string;
  avatarStatic?: string;
  logo?: string;
}

export interface PersonalityBrand {
  primaryColor?: string;
  font?: string;
}

/** A chat message in a conversation thread. */
/** A single typed content block within an assistant message. */
export interface ContentBlock {
  type: string;
  text?: string;
  format?: string;
  version?: string;
  data?: Record<string, unknown>;
  rendererHint?: string;
  url?: string;
  alt?: string;
  height?: number;
  width?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  timestamp: number;
  /** Ordered content blocks (when available from done payload). */
  contentBlocks?: ContentBlock[];
}

/** Options for the agent chat hook. */
export interface AgentChatOptions {
  /** Nexo API base URL. */
  apiBaseUrl: string;
  /** Bearer token for API auth. */
  accessToken: string;
  /** The app's UUID (from domain-session response). */
  appId: string;
  /** Current user ID (from domain-session response). */
  userId: string;
  /** App slug for canonical /api/apps/{slug} routing. Required - the backend
   *  only serves agent routes at slug-based paths. */
  slug: string;
  /** Optional capability filter for the agent. */
  capabilityName?: string;
  /** Storage key prefix for thread persistence. */
  storagePrefix?: string;
  /** Optional device key for guest -> authenticated thread migration. */
  deviceKey?: string | null;
  /** Optional agent card URL for initial prompt suggestion bootstrap. */
  agentCardUrl?: string | null;
  /** Locale hint sent with messages. */
  locale?: string;
}

/** Return type of useAgentChat. */
export interface AgentChatResult {
  messages: ChatMessage[];
  sending: boolean;
  progress: string | null;
  error: string | null;
  suggestions: string[];
  sendMessage: (text: string) => Promise<void>;
  clearThread: () => void;
}
