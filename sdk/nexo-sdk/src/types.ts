/**
 * Shared types for the Nexo SDK.
 *
 * These are the contracts between a Nexo-hosted frontend app and the
 * Nexo backend. They are stable across all apps (nutrition, todo, etc.).
 */

/** Bootstrap message received from the Nexo launch page via postMessage. */
export interface NexoBootstrap {
  type: "nexo:bootstrap";
  app_id: string;
  slug: string;
  app_name: string;
  api_base_url: string;
  access_token: string;
  user_id: string;
  locale: string | null;
  surface_mode: string | null;
  capabilities: Record<string, unknown>;
}

/** Resolved client configuration after auth. */
export interface NexoClientConfig {
  apiBaseUrl: string;
  appId: string;
  slug: string;
  accessToken: string | null;
  userId: string;
  /** Base URL of the Nexo hosted auth/profile/onboarding service. */
  authBaseUrl?: string | null;
  /** Request transport used by the runtime client. */
  runtimeAuthMode?: NexoRuntimeAuthMode;
  /** Current auth mode - guest or authenticated. Defaults to "guest". */
  authMode?: "guest" | "authenticated";
  /** Current access state (auth bridge only). */
  accessState?: "access_granted" | "access_pending" | "invite_code_required" | "invite_required" | null;
  /** Device key for thread recovery across sessions (auth bridge only). */
  deviceKey?: string;
}

/** Per-environment entry in nexo.json. */
export interface NexoSiteEnvironmentConfig {
  app_id?: string;
  api_base_url?: string;
  /** Base URL of the Nexo hosted auth service for this environment. */
  auth_base_url?: string;
}

/** Public nexo.json schema. */
export interface NexoSiteConfig {
  slug?: string;
  app_id?: string;
  environments?: Record<string, NexoSiteEnvironmentConfig>;
}

export type NexoAuthMode = "guest" | "authenticated";
export type NexoRuntimeAuthMode = "bearer" | "hosted_session";
export type NexoAccessState =
  | "access_granted"
  | "access_pending"
  | "invite_code_required"
  | "invite_required";

/** Options for auth bridge integration. */
export interface NexoAuthBridgeOptions {
  /** Whether to check for auth bridge session during init. */
  enabled: boolean;
  /** Base URL of the app's own server for prepare/session endpoints. */
  serviceBaseUrl?: string;
}

/** Options for creating a Nexo client instance. */
export interface NexoClientOptions {
  /** Prefix for localStorage keys (e.g. "nutrition" -> "nexo_nutrition_token"). */
  storagePrefix: string;
  /** Enable auth bridge for guest-to-authenticated transitions. */
  authBridge?: NexoAuthBridgeOptions;
}
