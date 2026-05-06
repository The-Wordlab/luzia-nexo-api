/**
 * Nexo API client.
 *
 * Creates and manages an authenticated connection to the Nexo backend.
 * Supports two init paths:
 *   1. Bootstrap (postMessage from Nexo launch page)
 *   2. Standalone (slug-native domain-verified session via nexo.json)
 *
 * Auth bridge extension (opt-in via `authBridge: { enabled: true }`):
 *   - Device key management for thread recovery
 *   - Session meta persistence
 *   - Guest-to-authenticated transitions via cookie-based session
 *
 * Usage (standalone app session):
 *   const nexo = createNexoClient({ storagePrefix: "nutrition" });
 *   await nexo.initStandalone("http://localhost:8000");
 *   const data = await nexo.get<MyType>("/api/apps/structured/tables/123/records");
 *
 * Usage (with auth bridge):
 *   const nexo = createNexoClient({
 *     storagePrefix: "myapp",
 *     authBridge: { enabled: true, serviceBaseUrl: "https://myapp.example.com" },
 *   });
 *   await nexo.initStandalone("http://localhost:8000");
 */

import type {
  NexoAuthMode,
  NexoAccessState,
  NexoBootstrap,
  NexoClientConfig,
  NexoClientOptions,
} from "./types";
import {
  loadNexoSiteConfig,
  resolveApiBaseUrlFromSiteConfig,
  resolveAuthBaseUrlFromSiteConfig,
} from "./site-config";

interface NexoQueryOverrides {
  apiBaseUrl: string | null;
  env: string | null;
}

interface AuthBridgeSessionPayload {
  access_token: string;
  user_id: string;
  app_id?: string;
  access_state?: string;
}

interface SessionMeta {
  appId: string;
  userId: string;
  authMode: NexoAuthMode;
  accessState: NexoAccessState | null;
  authBaseUrl: string | null;
  deviceKey: string;
}

export interface NexoClient {
  /** Initialize from a postMessage bootstrap payload. */
  initFromBootstrap(bootstrap: NexoBootstrap): void;

  /** Initialize in standalone mode via slug-native domain-verified session. */
  initStandalone(fallbackApiBaseUrl: string): Promise<NexoClientConfig>;

  /** Get the resolved client config. Throws if not initialized. */
  getConfig(): NexoClientConfig;

  /** Get the app_id from session or bootstrap. */
  getAppId(): string;

  /** Whether the client has been initialized. */
  isInitialized(): boolean;

  /**
   * Hydrate the client from localStorage (no network calls).
   *
   * When NexoAppShell manages the connection, the app's module-level
   * client can call this to pick up the shell's cached credentials.
   * Returns true if credentials were found and the client is now ready.
   */
  hydrateFromStorage(): Promise<boolean>;

  /** Get the auth mode (guest or authenticated). Defaults to "guest". */
  getAuthMode(): NexoAuthMode;

  /** Get the current access state. */
  getAccessState(): NexoAccessState | null;

  /** Clear stored session tokens and metadata. */
  clearStoredSession(options?: { clearDeviceKey?: boolean }): void;

  /** Build the URL to start auth bridge login flow (server-backed apps). */
  buildAuthBridgeStartUrl(nextPath?: string): string;

  /** Prepare and return the auth bridge start URL (saves guest token for migration). */
  prepareAuthBridgeStart(nextPath?: string): Promise<string>;

  /** Build the URL to start Nexo-hosted login (serverless/CDN apps). */
  buildNexoLoginUrl(): string;

  /** Build the URL to open the Nexo-hosted profile surface for this app. */
  buildNexoProfileUrl(nextPath?: string): string;

  /** Build the URL to open the Nexo-hosted onboarding surface for this app. */
  buildNexoOnboardingUrl(nextPath?: string): string;

  /** Authenticated GET request. */
  get<T = unknown>(path: string): Promise<T>;

  /** Authenticated POST request. */
  post<T = unknown>(path: string, body: unknown): Promise<T>;

  /** Authenticated PATCH request. */
  patch<T = unknown>(path: string, body: unknown): Promise<T>;

  /** Authenticated DELETE request. */
  del(path: string): Promise<void>;
}

export function resolveNexoQueryOverrides(search: string): NexoQueryOverrides {
  const params = new URLSearchParams(search);
  return {
    apiBaseUrl: params.get("nexo_api"),
    env: params.get("nexo_env"),
  };
}

function extractUserId(token: string): string {
  try {
    return JSON.parse(atob(token.split(".")[1])).sub || "";
  } catch {
    return "";
  }
}

function getLocationTokenParam(key: string): string | null {
  const searchValue = new URLSearchParams(window.location.search).get(key);
  if (searchValue) {
    return searchValue;
  }

  const rawHash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!rawHash) {
    return null;
  }
  return new URLSearchParams(rawHash).get(key);
}

function clearLocationTokenParam(key: string): void {
  const cleanUrl = new URL(window.location.href);
  cleanUrl.searchParams.delete(key);

  const rawHash = cleanUrl.hash.startsWith("#")
    ? cleanUrl.hash.slice(1)
    : cleanUrl.hash;
  if (rawHash) {
    const hashParams = new URLSearchParams(rawHash);
    hashParams.delete(key);
    const nextHash = hashParams.toString();
    cleanUrl.hash = nextHash ? `#${nextHash}` : "";
  }

  window.history.replaceState({}, "", cleanUrl.toString());
}

function makeWebDeviceKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `web-${crypto.randomUUID()}`;
  }
  return `web-${Date.now()}`;
}

function normalizeAccessState(rawValue: string | null | undefined): NexoAccessState | null {
  switch (rawValue) {
    case "access_granted":
    case "access_pending":
    case "invite_code_required":
    case "invite_required":
      return rawValue;
    default:
      return null;
  }
}

/**
 * Create a Nexo client instance.
 *
 * Each app creates its own instance with a unique storagePrefix so
 * localStorage tokens don't collide between apps on the same domain.
 */
export function createNexoClient(options: NexoClientOptions): NexoClient {
  const tokenKey = `nexo_${options.storagePrefix}_token`;
  const userKey = `nexo_${options.storagePrefix}_user_id`;
  const sessionMetaKey = `nexo_${options.storagePrefix}_session_meta`;
  const deviceKeyStorageKey = `nexo_${options.storagePrefix}_device_key`;

  const authBridgeEnabled = options.authBridge?.enabled === true;
  const serviceBaseUrl = options.authBridge?.serviceBaseUrl;

  let _config: NexoClientConfig | null = null;

  // --- Device key management (auth bridge only) ---

  function getOrCreateDeviceKey(): string {
    const stored = localStorage.getItem(deviceKeyStorageKey);
    if (stored) return stored;
    const created = makeWebDeviceKey();
    localStorage.setItem(deviceKeyStorageKey, created);
    return created;
  }

  // --- Session meta persistence (auth bridge only) ---

  function persistSessionMeta(meta: SessionMeta): void {
    localStorage.setItem(sessionMetaKey, JSON.stringify(meta));
  }

  function loadSessionMeta(): SessionMeta | null {
    const stored = localStorage.getItem(sessionMetaKey);
    if (!stored) return null;

    try {
      const parsed = JSON.parse(stored) as Partial<SessionMeta>;
      if (
        typeof parsed.appId !== "string" ||
        typeof parsed.userId !== "string" ||
        (parsed.authMode !== "guest" && parsed.authMode !== "authenticated") ||
        typeof parsed.deviceKey !== "string"
      ) {
        return null;
      }

      return {
        appId: parsed.appId,
        userId: parsed.userId,
        authMode: parsed.authMode,
        accessState: normalizeAccessState(parsed.accessState ?? null),
        authBaseUrl:
          typeof parsed.authBaseUrl === "string" && parsed.authBaseUrl
            ? parsed.authBaseUrl
            : null,
        deviceKey: parsed.deviceKey,
      };
    } catch {
      return null;
    }
  }

  // --- Config resolution ---

  async function resolveConfigFromSite(): Promise<{
    slug: string;
    apiBaseUrl: string;
    authBaseUrl: string | null;
  } | null> {
    const queryOverrides = resolveNexoQueryOverrides(window.location.search);
    const siteConfig = await loadNexoSiteConfig();
    const hostOptions = {
      host: window.location.host,
      envHint: queryOverrides.env,
    };
    const apiBaseUrl =
      queryOverrides.apiBaseUrl ||
      resolveApiBaseUrlFromSiteConfig(siteConfig, hostOptions);
    if (!apiBaseUrl) return null;

    const slug = siteConfig?.slug;
    if (!slug) return null;

    const authBaseUrl = authBridgeEnabled
      ? resolveAuthBaseUrlFromSiteConfig(siteConfig, hostOptions)
      : null;

    return { slug, apiBaseUrl, authBaseUrl };
  }

  // --- Auth bridge session resolution ---

  function buildAuthBridgeSessionUrls(): string[] {
    const urls: string[] = [];
    if (serviceBaseUrl) {
      urls.push(new URL("/auth/nexo/session", serviceBaseUrl).toString());
    }
    const sameOriginUrl = new URL("/auth/nexo/session", window.location.origin).toString();
    if (!urls.includes(sameOriginUrl)) {
      urls.push(sameOriginUrl);
    }
    return urls;
  }

  async function resolveAuthBridgeSession(): Promise<AuthBridgeSessionPayload | null> {
    for (const sessionUrl of buildAuthBridgeSessionUrls()) {
      try {
        const response = await fetch(sessionUrl, {
          cache: "no-store",
          credentials: "include",
        });
        if (response.status === 204) {
          return null;
        }
        if (!response.ok) {
          continue;
        }
        if (!(response.headers.get("content-type") || "").includes("application/json")) {
          continue;
        }

        const payload = (await response.json()) as Partial<AuthBridgeSessionPayload>;
        if (
          typeof payload.access_token === "string" &&
          typeof payload.user_id === "string"
        ) {
          return {
            access_token: payload.access_token,
            user_id: payload.user_id,
            app_id: typeof payload.app_id === "string" ? payload.app_id : undefined,
            access_state:
              typeof payload.access_state === "string" ? payload.access_state : undefined,
          };
        }
      } catch {
        // Try the next auth-bridge endpoint candidate.
      }
    }
    return null;
  }

  async function validateCachedAccessToken(
    apiBaseUrl: string,
    accessToken: string,
  ): Promise<boolean> {
    try {
      const response = await fetch(`${apiBaseUrl}/api/me/account`, {
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: "no-store",
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  // --- Init ---

  function initFromBootstrap(bootstrap: NexoBootstrap): void {
    if (authBridgeEnabled) {
      const deviceKey = getOrCreateDeviceKey();
      persistSessionMeta({
        appId: bootstrap.app_id ?? "",
        userId: bootstrap.user_id,
        authMode: "authenticated",
        accessState: "access_granted",
        authBaseUrl: null,
        deviceKey,
      });
      _config = {
        apiBaseUrl: bootstrap.api_base_url,
        appId: bootstrap.app_id ?? "",
        slug: bootstrap.slug,
        accessToken: bootstrap.access_token,
        userId: bootstrap.user_id,
        authBaseUrl: null,
        authMode: "authenticated",
        accessState: "access_granted",
        deviceKey,
      };
    } else {
      // Persist token so the app's module-level client can hydrate from storage
      localStorage.setItem(tokenKey, bootstrap.access_token);
      localStorage.setItem(userKey, bootstrap.user_id);
      _config = {
        apiBaseUrl: bootstrap.api_base_url,
        appId: bootstrap.app_id ?? "",
        slug: bootstrap.slug,
        accessToken: bootstrap.access_token,
        userId: bootstrap.user_id,
      };
    }
  }

  async function initStandalone(
    fallbackApiBaseUrl: string,
  ): Promise<NexoClientConfig> {
    // Dev convenience: ?token= skips domain verification
    const tokenParam = new URLSearchParams(window.location.search).get("token");
    if (tokenParam) {
      const userId = extractUserId(tokenParam);
      const resolved = await resolveConfigFromSite();
      const slug = resolved?.slug ?? "";
      if (authBridgeEnabled) {
        const deviceKey = getOrCreateDeviceKey();
        _config = {
          apiBaseUrl: fallbackApiBaseUrl,
          appId: "",
          slug,
          accessToken: tokenParam,
          userId,
          authBaseUrl: null,
          authMode: "guest",
          accessState: null,
          deviceKey,
        };
      } else {
        _config = {
          apiBaseUrl: fallbackApiBaseUrl,
          appId: "",
          slug,
          accessToken: tokenParam,
          userId,
        };
      }
      return _config;
    }

    // Nexo-hosted redirect login: ?nexo_token= after Nexo login redirect.
    // For CDN-hosted apps that redirect to Nexo for Google/Apple login
    // and receive the JWT back via URL parameter.
    const nexoTokenParam = getLocationTokenParam("nexo_token");
    if (nexoTokenParam) {
      // Clean the token from the URL immediately (security + UX)
      clearLocationTokenParam("nexo_token");

      const resolved = await resolveConfigFromSite();
      if (!resolved) {
        throw new Error(
          `No nexo.json found or no environment configured for ${window.location.host}.`,
        );
      }

      const userId = extractUserId(nexoTokenParam);
      const { slug, apiBaseUrl, authBaseUrl } = resolved;

      localStorage.setItem(tokenKey, nexoTokenParam);
      localStorage.setItem(userKey, userId);

      if (authBridgeEnabled) {
        const deviceKey = getOrCreateDeviceKey();
        persistSessionMeta({
          appId: "",
          userId,
          authMode: "authenticated",
          accessState: "access_granted",
          authBaseUrl,
          deviceKey,
        });
        _config = {
          apiBaseUrl,
          appId: "",
          slug,
          accessToken: nexoTokenParam,
          userId,
          authBaseUrl,
          authMode: "authenticated",
          accessState: "access_granted",
          deviceKey,
        };
      } else {
        _config = { apiBaseUrl, appId: "", slug, accessToken: nexoTokenParam, userId };
      }
      return _config;
    }

    if (authBridgeEnabled) {
      return initStandaloneWithAuthBridge();
    }

    return initStandaloneGuest();
  }

  async function initStandaloneWithAuthBridge(): Promise<NexoClientConfig> {
    // Check for auth_error query param
    const authBridgeError = new URLSearchParams(window.location.search).get("auth_error");
    if (authBridgeError) {
      throw new Error(authBridgeError);
    }

    const deviceKey = getOrCreateDeviceKey();

    const resolved = await resolveConfigFromSite();
    if (!resolved) {
      throw new Error(
        `No nexo.json found or no environment configured for ${window.location.host}. ` +
          "Launch this app through Nexo or configure the site config file.",
      );
    }

    const { slug, apiBaseUrl, authBaseUrl } = resolved;

    // Check auth bridge session (cookie-based)
    const authBridgeSession = await resolveAuthBridgeSession();
    if (authBridgeSession) {
      const accessToken = authBridgeSession.access_token;
      const userId = authBridgeSession.user_id;
      const resolvedAppId = authBridgeSession.app_id || "";
      const accessState =
        normalizeAccessState(authBridgeSession.access_state) || "access_granted";

      localStorage.setItem(tokenKey, accessToken);
      localStorage.setItem(userKey, userId);
      persistSessionMeta({
        appId: resolvedAppId,
        userId,
        authMode: "authenticated",
        accessState,
        authBaseUrl,
        deviceKey,
      });
      _config = {
        apiBaseUrl,
        appId: resolvedAppId,
        slug,
        accessToken,
        userId,
        authBaseUrl,
        authMode: "authenticated",
        accessState,
        deviceKey,
      };
      return _config;
    }

    // Check cached token + validate against /api/me/account
    const cached = localStorage.getItem(tokenKey);
    const cachedUser = localStorage.getItem(userKey);
    const sessionMeta = loadSessionMeta();
    if (cached && cachedUser && (await validateCachedAccessToken(apiBaseUrl, cached))) {
      const cachedAppId = sessionMeta?.appId || "";
      const cachedAuthMode = sessionMeta?.authMode ?? "guest";
      const cachedAccessState =
        cachedAuthMode === "authenticated"
          ? sessionMeta?.accessState || "access_granted"
          : null;

      persistSessionMeta({
        appId: cachedAppId,
        userId: cachedUser,
        authMode: cachedAuthMode,
        accessState: cachedAccessState,
        authBaseUrl,
        deviceKey: sessionMeta?.deviceKey || deviceKey,
      });
      _config = {
        apiBaseUrl,
        appId: cachedAppId,
        slug,
        accessToken: cached,
        userId: cachedUser,
        authBaseUrl,
        authMode: cachedAuthMode,
        accessState: cachedAccessState,
        deviceKey: sessionMeta?.deviceKey || deviceKey,
      };
      return _config;
    }

    // Fall back to slug-native domain-verified session with device_key
    const persona = new URLSearchParams(window.location.search).get("persona");
    const params = new URLSearchParams();
    if (persona) params.set("persona", persona);
    params.set("device_key", deviceKey);
    const url = `${apiBaseUrl}/api/apps/${slug}/domain-session?${params.toString()}`;

    const resp = await fetch(url, { method: "POST" });
    if (resp.ok) {
      const data = await resp.json();
      localStorage.setItem(tokenKey, data.access_token);
      localStorage.setItem(userKey, data.user_id);
      persistSessionMeta({
        appId: data.app_id ?? "",
        userId: data.user_id,
        authMode: "guest",
        accessState: null,
        authBaseUrl,
        deviceKey,
      });
      _config = {
        apiBaseUrl,
        appId: data.app_id ?? "",
        slug,
        accessToken: data.access_token,
        userId: data.user_id,
        authBaseUrl,
        authMode: "guest",
        accessState: null,
        deviceKey,
      };
      return _config;
    }

    const err = await resp.json().catch(() => ({ detail: `Status ${resp.status}` }));
    throw new Error(err.detail || `Domain session failed: ${resp.status}`);
  }

  async function initStandaloneGuest(): Promise<NexoClientConfig> {
    const resolved = await resolveConfigFromSite();
    if (!resolved) {
      throw new Error(
        `No nexo.json found or no environment configured for ${window.location.host}. ` +
          "Launch this app through Nexo or configure the site config file.",
      );
    }

    const { slug, apiBaseUrl, authBaseUrl } = resolved;

    // Check cached token
    const cached = localStorage.getItem(tokenKey);
    const cachedUser = localStorage.getItem(userKey);
    if (cached && cachedUser) {
      try {
        const resp = await fetch(`${apiBaseUrl}/api/apps/${slug}/bootstrap`, {
          headers: { Authorization: `Bearer ${cached}` },
        });
        if (resp.ok) {
          const bootstrap = await resp.json();
          _config = { apiBaseUrl, appId: bootstrap.app_id ?? "", slug, accessToken: cached, userId: cachedUser, authBaseUrl };
          return _config;
        }
      } catch {
        // Expired or invalid - fall through to domain session
      }
    }

    // Request slug-native domain-verified session
    const persona = new URLSearchParams(window.location.search).get("persona");
    const url = `${apiBaseUrl}/api/apps/${slug}/domain-session${
      persona ? `?persona=${encodeURIComponent(persona)}` : ""
    }`;

    const resp = await fetch(url, { method: "POST" });
    if (resp.ok) {
      const data = await resp.json();
      localStorage.setItem(tokenKey, data.access_token);
      localStorage.setItem(userKey, data.user_id);
      _config = {
        apiBaseUrl,
        appId: data.app_id ?? "",
        slug,
        accessToken: data.access_token,
        userId: data.user_id,
        authBaseUrl,
      };
      return _config;
    }

    const err = await resp.json().catch(() => ({ detail: `Status ${resp.status}` }));
    throw new Error(err.detail || `Domain session failed: ${resp.status}`);
  }

  // --- Accessors ---

  function getConfig(): NexoClientConfig {
    if (!_config) throw new Error("Nexo client not initialized");
    return _config;
  }

  function getAppId(): string {
    return getConfig().appId;
  }

  function isInitialized(): boolean {
    return _config !== null;
  }

  async function hydrateFromStorage(): Promise<boolean> {
    if (_config) return true;

    const cached = localStorage.getItem(tokenKey);
    const cachedUser = localStorage.getItem(userKey);
    if (!cached || !cachedUser) return false;

    // Resolve API base URL and slug from nexo.json (local read, no network)
    const resolved = await resolveConfigFromSite();
    if (!resolved) return false;

    const { slug, apiBaseUrl, authBaseUrl } = resolved;
    _config = {
      apiBaseUrl,
      appId: "", // Will be populated by bootstrap call if needed
      slug,
      accessToken: cached,
      userId: cachedUser,
      authBaseUrl,
    };

    // Try bootstrap to get app_id (one lightweight call)
    try {
      const resp = await fetch(`${apiBaseUrl}/api/apps/${slug}/bootstrap`, {
        headers: { Authorization: `Bearer ${cached}` },
      });
      if (resp.ok) {
        const bootstrap = await resp.json();
        _config.appId = bootstrap.app_id ?? "";
      }
    } catch {
      // Bootstrap failed but we have enough to make API calls
    }

    return true;
  }

  function getAuthMode(): NexoAuthMode {
    return getConfig().authMode ?? "guest";
  }

  function getAccessState(): NexoAccessState | null {
    return getConfig().accessState ?? null;
  }

  // --- Auth bridge actions ---

  function resolveServiceBaseUrl(): string {
    return serviceBaseUrl || window.location.origin;
  }

  function buildAuthBridgeStartUrl(nextPath?: string): string {
    const config = getConfig();
    if (!config.authBaseUrl) {
      throw new Error("ERROR_AUTH_BRIDGE_UNAVAILABLE");
    }
    if (!config.slug) {
      throw new Error("ERROR_APP_SLUG_NOT_CONFIGURED");
    }
    const normalizedNext =
      !nextPath || !nextPath.startsWith("/") || nextPath.startsWith("//")
        ? "/"
        : nextPath;
    const callbackUrl = new URL("/auth/nexo/callback", resolveServiceBaseUrl()).toString();
    const url = new URL(
      `/apps/${encodeURIComponent(config.slug)}/auth`,
      config.authBaseUrl,
    );
    url.searchParams.set("return_to", callbackUrl);
    if (config.deviceKey) {
      url.searchParams.set("device_key", config.deviceKey);
    }
    url.searchParams.set("next", normalizedNext);
    return url.toString();
  }

  async function prepareAuthBridgeStart(nextPath?: string): Promise<string> {
    const config = getConfig();
    const startUrl = buildAuthBridgeStartUrl(nextPath);

    if (config.authMode !== "guest") {
      return startUrl;
    }

    const prepareUrl = new URL("/auth/nexo/prepare", resolveServiceBaseUrl()).toString();
    const response = await fetch(prepareUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ guest_token: config.accessToken }),
    });

    if (!response.ok) {
      throw new Error("ERROR_AUTH_BRIDGE_SESSION_UNAVAILABLE");
    }

    return startUrl;
  }

  function buildNexoLoginUrl(): string {
    return buildNexoHostedAppUrl("auth");
  }

  function buildNexoProfileUrl(nextPath?: string): string {
    return buildNexoHostedAppUrl("profile", nextPath);
  }

  function buildNexoOnboardingUrl(nextPath?: string): string {
    return buildNexoHostedAppUrl("onboarding", nextPath);
  }

  function buildNexoHostedAppUrl(
    route: "auth" | "profile" | "onboarding",
    nextPath?: string,
  ): string {
    const config = getConfig();
    const authBase = config.authBaseUrl;
    if (!authBase) {
      throw new Error("ERROR_AUTH_BASE_URL_NOT_CONFIGURED");
    }
    if (!config.slug) {
      throw new Error("ERROR_APP_SLUG_NOT_CONFIGURED");
    }
    const currentLocation = window.location;
    const defaultReturnTo = `${currentLocation.origin}${currentLocation.pathname}${currentLocation.search ?? ""}${currentLocation.hash ?? ""}`;
    const normalizedNext =
      nextPath && nextPath.startsWith("/") && !nextPath.startsWith("//")
        ? nextPath
        : defaultReturnTo;
    const url = new URL(`/apps/${encodeURIComponent(config.slug)}/${route}`, authBase);
    url.searchParams.set("return_to", normalizedNext);
    return url.toString();
  }

  function clearStoredSession(options?: { clearDeviceKey?: boolean }): void {
    localStorage.removeItem(tokenKey);
    localStorage.removeItem(userKey);
    localStorage.removeItem(sessionMetaKey);
    if (options?.clearDeviceKey) {
      localStorage.removeItem(deviceKeyStorageKey);
    }
    _config = null;
  }

  // --- HTTP methods ---

  async function get<T = unknown>(path: string): Promise<T> {
    const { apiBaseUrl, accessToken } = getConfig();
    const resp = await fetch(`${apiBaseUrl}${path}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) throw new Error(`GET ${path} failed: ${resp.status}`);
    return resp.json();
  }

  async function post<T = unknown>(path: string, body: unknown): Promise<T> {
    const { apiBaseUrl, accessToken } = getConfig();
    const resp = await fetch(`${apiBaseUrl}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`POST ${path} failed: ${resp.status}`);
    return resp.json();
  }

  async function patch<T = unknown>(path: string, body: unknown): Promise<T> {
    const { apiBaseUrl, accessToken } = getConfig();
    const resp = await fetch(`${apiBaseUrl}${path}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`PATCH ${path} failed: ${resp.status}`);
    return resp.json();
  }

  async function del(path: string): Promise<void> {
    const { apiBaseUrl, accessToken } = getConfig();
    const resp = await fetch(`${apiBaseUrl}${path}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) throw new Error(`DELETE ${path} failed: ${resp.status}`);
  }

  return {
    initFromBootstrap,
    initStandalone,
    getConfig,
    getAppId,
    isInitialized,
    hydrateFromStorage,
    getAuthMode,
    getAccessState,
    clearStoredSession,
    buildAuthBridgeStartUrl,
    prepareAuthBridgeStart,
    buildNexoLoginUrl,
    buildNexoProfileUrl,
    buildNexoOnboardingUrl,
    get,
    post,
    patch,
    del,
  };
}
