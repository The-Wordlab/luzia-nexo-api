/**
 * React hooks and components for the Nexo SDK.
 *
 * Separated from the core module so non-React consumers
 * (scripts, Node, etc.) don't need React as a dependency.
 */

// Hooks
export { useNexoBootstrap } from "./useNexoBootstrap";
export { useAgentChat } from "./useAgentChat";
export { useHashRoute } from "./useHashRoute";
export {
  buildAgentThreadStorageKey,
  buildAgentDeviceThreadStorageKey,
  clearAgentThreadStorage,
  clearAgentThreadStorageForApp,
  migrateAgentThreadStorage,
  extractPromptSuggestionsFromAgentCard,
  loadAgentPromptSuggestions,
} from "./agent-utils";

// Agent chat components
export { AgentChatBubble } from "./components/AgentChatBubble";
export type { AgentChatBubbleProps } from "./components/AgentChatBubble";
export { AgentChatPanel } from "./components/AgentChatPanel";
export type { AgentChatPanelProps } from "./components/AgentChatPanel";
export { AgentChatFab } from "./components/AgentChatFab";
export type { AgentChatFabProps } from "./components/AgentChatFab";
export { AgentSuggestionChips } from "./components/AgentSuggestionChips";
export type { AgentSuggestionChipsProps } from "./components/AgentSuggestionChips";

// Personality components
export { PersonalitySelector, PersonalityOption } from "./components/PersonalitySelector";
export type { PersonalitySelectorProps, PersonalityOptionProps } from "./components/PersonalitySelector";

// Auth components
export { NexoAuthEntryButton } from "./components/NexoAuthEntryButton";
export type { NexoAuthEntryButtonProps } from "./components/NexoAuthEntryButton";
export { NexoAuthStatusCard } from "./components/NexoAuthStatusCard";
export type { NexoAuthStatusCardProps, NexoAuthStatusLabels } from "./components/NexoAuthStatusCard";

// Shell
export { NexoAppShell } from "./components/NexoAppShell";
export type {
  NexoAppShellProps,
  NexoAppShellContext,
  NexoAppShellLabels,
} from "./components/NexoAppShell";

// Auth types from canonical source (not from components)
export type { NexoAuthMode, NexoAccessState } from "./types";

// Types re-exported for convenience
export type {
  ChatMessage,
  AgentChatOptions,
  AgentChatResult,
  ContentBlock,
  Personality,
  PersonalityAssets,
  PersonalityBrand,
} from "./chat-types";
