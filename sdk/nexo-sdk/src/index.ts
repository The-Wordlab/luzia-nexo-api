/**
 * @luzia/nexo-sdk - Client SDK for Nexo-hosted frontend apps.
 *
 * Core entrypoint (no React dependency).
 * For React hooks, import from "@luzia/nexo-sdk/react".
 */

// Client
export { createNexoClient, resolveNexoQueryOverrides } from "./client";
export type { NexoClient } from "./client";

// Site config
export {
  loadNexoSiteConfig,
  resolveApiBaseUrlFromSiteConfig,
  resolveAuthBaseUrlFromSiteConfig,
  resolveAppIdFromSiteConfig,
  extractTrustedOriginsFromSiteConfig,
} from "./site-config";

// i18n
export {
  createI18n,
  resolveLocale,
  isSupported,
  SUPPORTED_LOCALES,
} from "./i18n";
export type { Locale } from "./i18n";

// Utilities
export { getQueryParam, unwrapRecords, resolveDemoPersonaId } from "./utils";

// Agent utilities
export {
  buildAgentThreadStorageKey,
  buildAgentDeviceThreadStorageKey,
  clearAgentThreadStorage,
  clearAgentThreadStorageForApp,
  migrateAgentThreadStorage,
  extractPromptSuggestionsFromAgentCard,
  loadAgentPromptSuggestions,
} from "./agent-utils";

// Types
export type {
  NexoBootstrap,
  NexoClientConfig,
  NexoClientOptions,
  NexoSiteConfig,
  NexoSiteEnvironmentConfig,
  NexoAuthMode,
  NexoAccessState,
  NexoAuthBridgeOptions,
} from "./types";
export type {
  ChatMessage,
  AgentAppearance,
  AgentChatOptions,
  AgentChatResult,
  Personality,
  PersonalityAssets,
  PersonalityBrand,
} from "./chat-types";
