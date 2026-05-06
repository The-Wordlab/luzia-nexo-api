/**
 * NexoAppShell - standard outer shell for Nexo-hosted apps.
 *
 * Provides:
 *   - Top toolbar (app name, login button, theme toggle, locale selector)
 *   - Loading and error states during connection setup
 *   - Webview mode detection (?webview=1 or postMessage bootstrap present)
 *   - Dark/light theme toggle (persisted to localStorage)
 *   - Locale selector (persisted to localStorage)
 *   - Optional AgentChatFab when agentCapability is provided
 *
 * All visible labels come from the `labels` prop - no hardcoded English.
 * Styling uses CSS class names only; host app provides the stylesheet.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createNexoClient } from "../client";
import { useNexoBootstrap } from "../useNexoBootstrap";
import { NexoAuthStatusCard } from "./NexoAuthStatusCard";
import { AgentChatFab } from "./AgentChatFab";
import { AgentChatPanel } from "./AgentChatPanel";
import { useAgentChat } from "../useAgentChat";
import type { NexoClientConfig, NexoAuthMode, NexoBootstrap } from "../types";
import type { NexoAccessState } from "../types";
import type { AgentChatOptions, Personality } from "../chat-types";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface NexoAppShellLabels {
  signInLabel: string;
  connecting: string;
  connectionError: string;
  connectionErrorHint: string;
  // Auth status labels
  accessPendingTitle: string;
  accessPendingDesc: string;
  inviteRequiredTitle: string;
  inviteRequiredDesc: string;
  inviteCodeRequiredTitle: string;
  inviteCodeRequiredDesc: string;
  // Agent chat labels (optional, only needed if agentCapability set)
  chatFabAriaLabel?: string;
  chatFabLabel?: string;
  chatTitle?: string;
  chatWelcomeTitle?: string;
  chatWelcomeDescription?: string;
  chatPlaceholder?: string;
  chatNewLabel?: string;
  chatClearLabel?: string;
  chatCloseLabel?: string;
}

export interface NexoAppShellContext {
  /** Whether the app is connected and ready. */
  isReady: boolean;
  /** Connection status: "connecting" | "connected" | "error". */
  connectionStatus: "connecting" | "connected" | "error";
  /** Connection error message (null unless connectionStatus is "error"). */
  connectionError: string | null;
  /** Current auth mode. */
  authMode: NexoAuthMode;
  /** Current locale. */
  locale: string;
  /** Whether dark mode is active. */
  darkMode: boolean;
  /** Toggle dark mode. */
  toggleDarkMode: () => void;
  /** Change the active locale. */
  setLocale: (locale: "en" | "es" | "pt" | "fr" | "it") => void;
  /** The resolved Nexo client config. */
  config: NexoClientConfig | null;
  /** Bootstrap payload (non-null in webview mode). */
  bootstrap: NexoBootstrap | null;
  /** Whether the shell is in webview mode. */
  isWebview: boolean;
}

export interface NexoAppShellProps {
  /** App display name shown in toolbar. */
  appName: string;
  /** Storage prefix for the Nexo client (e.g. "nutrition"). */
  storagePrefix: string;
  /** Nexo API fallback URL for standalone mode. */
  apiBaseUrl?: string;
  /** Agent chat capability name (e.g. "nutrition.ask_expert"). Optional. */
  agentCapability?: string;
  /**
   * Custom avatar for the chat FAB. Can be:
   * - A URL to an image (character icon, SVG, PNG)
   * - An emoji string
   * - undefined (uses personality avatar or default chat bubble)
   */
  chatFabAvatar?: string;
  /** The app content to render inside the shell. */
  children: React.ReactNode | ((context: NexoAppShellContext) => React.ReactNode);
  /** Labels for shell UI text. */
  labels: NexoAppShellLabels;
  /**
   * Called synchronously when the user changes locale via the shell selector.
   * Use this to sync your app's i18n module (e.g. setLocale()) so the next
   * render uses the correct translations.
   */
  onLocaleChange?: (locale: string) => void;
  /** Additional CSS class on the shell container. */
  className?: string;
  /**
   * Replace the default toolbar-right controls (theme toggle, locale, login)
   * with custom content. Receives the shell context and default handlers.
   */
  renderToolbarRight?: (ctx: NexoAppShellContext & {
    onThemeToggle: () => void;
    onStartLogin: () => void;
    onLocaleChange: (locale: "en" | "es" | "pt" | "fr" | "it") => void;
  }) => React.ReactNode;
  /** Hide the default toolbar entirely (e.g. when the app renders its own). */
  hideToolbar?: boolean;
  /**
   * Skip all default chrome (loading, error, toolbar). The shell only manages
   * connection state, theme, and locale. Children always render and receive the
   * full context including connectionStatus so they can show their own UI.
   */
  skipDefaultChrome?: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SUPPORTED_LOCALES = ["en", "es", "pt", "fr", "it"] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

const LOCALE_LABELS: Record<SupportedLocale, string> = {
  en: "English",
  es: "Espa\u00f1ol",
  pt: "Portugu\u00eas",
  fr: "Fran\u00e7ais",
  it: "Italiano",
};

const LOCALE_FLAGS: Record<SupportedLocale, string> = {
  en: "\uD83C\uDDEC\uD83C\uDDE7",
  es: "\uD83C\uDDEA\uD83C\uDDF8",
  pt: "\uD83C\uDDE7\uD83C\uDDF7",
  fr: "\uD83C\uDDEB\uD83C\uDDF7",
  it: "\uD83C\uDDEE\uD83C\uDDF9",
};

const THEME_STORAGE_KEY = "nexo_theme";
const LOCALE_STORAGE_KEY = "nexo_locale";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resolveInitialTheme(): "light" | "dark" {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
    if (typeof window !== "undefined" && window.matchMedia) {
      return window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
  } catch {
    // localStorage unavailable
  }
  return "light";
}

function resolveInitialLocale(): SupportedLocale {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored && SUPPORTED_LOCALES.includes(stored as SupportedLocale)) {
      return stored as SupportedLocale;
    }
    // Check query param
    if (typeof window !== "undefined") {
      const param = new URLSearchParams(window.location.search).get("locale");
      if (param && SUPPORTED_LOCALES.includes(param as SupportedLocale)) {
        return param as SupportedLocale;
      }
    }
  } catch {
    // localStorage unavailable
  }
  return "en";
}

function isWebviewQueryParam(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("webview") === "1";
}

function syncThemeToDocument(theme: "light" | "dark"): void {
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }
}

// ---------------------------------------------------------------------------
// Sun/moon icons (inline SVG, no external dependency)
// ---------------------------------------------------------------------------

function SunIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Locale dropdown (custom, with flag emojis)
// ---------------------------------------------------------------------------

function LocaleDropdown({
  locale,
  onSelect,
}: {
  locale: SupportedLocale;
  onSelect: (loc: SupportedLocale) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleSelect = useCallback(
    (loc: SupportedLocale) => {
      onSelect(loc);
      setOpen(false);
    },
    [onSelect],
  );

  return (
    <div className="nexo-locale-dropdown" ref={ref}>
      <button
        type="button"
        className={`nexo-locale-trigger ${open ? "nexo-locale-trigger--open" : ""}`}
        onClick={() => setOpen(!open)}
      >
        <GlobeIcon />
        <ChevronDownIcon />
      </button>

      {open && (
        <div className="nexo-locale-menu">
          {SUPPORTED_LOCALES.map((loc) => (
            <button
              key={loc}
              type="button"
              className={`nexo-locale-option ${loc === locale ? "nexo-locale-option--active" : ""}`}
              onClick={() => handleSelect(loc)}
            >
              <span className="nexo-locale-option__flag">{LOCALE_FLAGS[loc]}</span>
              <span>{LOCALE_LABELS[loc]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type ConnectionStatus = "connecting" | "connected" | "error";

export function NexoAppShell({
  appName,
  storagePrefix,
  apiBaseUrl = "",
  agentCapability,
  chatFabAvatar,
  children,
  labels,
  className,
  renderToolbarRight,
  hideToolbar,
  skipDefaultChrome,
  onLocaleChange: onLocaleChangeProp,
}: NexoAppShellProps) {

  // Client is created once per mount. We use a ref so it survives re-renders.
  const clientRef = useRef(createNexoClient({ storagePrefix }));
  const client = clientRef.current;

  const bootstrap = useNexoBootstrap();

  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("connecting");
  const [connectionErrorMsg, setConnectionErrorMsg] = useState<string | null>(
    null,
  );
  const [config, setConfig] = useState<NexoClientConfig | null>(null);
  const [loginPending, setLoginPending] = useState(false);

  // Theme and locale state - read from localStorage on mount
  const [darkMode, setDarkMode] = useState<boolean>(
    () => resolveInitialTheme() === "dark",
  );
  const [locale, setLocale] = useState<SupportedLocale>(
    () => resolveInitialLocale(),
  );

  // Webview detection: bootstrap present OR ?webview=1 query param
  const isWebview = useMemo(
    () => bootstrap !== null || isWebviewQueryParam(),
    [bootstrap],
  );

  // Sync dark class on <html> whenever darkMode changes
  useEffect(() => {
    syncThemeToDocument(darkMode ? "dark" : "light");
  }, [darkMode]);

  // Initialize the client on mount
  useEffect(() => {
    if (bootstrap) {
      // Webview mode - use bootstrap payload
      client.initFromBootstrap(bootstrap);
      try {
        setConfig(client.getConfig());
      } catch {
        // getConfig may fail if init had issues; still treat as connected
      }
      setConnectionStatus("connected");
      return;
    }

    // Standalone mode - initialize via domain session
    client
      .initStandalone(apiBaseUrl || window.location.origin)
      .then((resolvedConfig) => {
        setConfig(resolvedConfig);
        setConnectionStatus("connected");
      })
      .catch((err: unknown) => {
        setConnectionErrorMsg(
          err instanceof Error ? err.message : labels.connectionError,
        );
        setConnectionStatus("error");
      });
  }, [bootstrap]); // eslint-disable-line react-hooks/exhaustive-deps
  // Note: client, apiBaseUrl, labels are stable for the lifetime of the shell.

  const authMode: NexoAuthMode = config?.authMode ?? "guest";
  const accessState: NexoAccessState | null = config?.accessState ?? null;
  const isReady = connectionStatus === "connected";

  // Agent chat options (only active when ready and agent configured)
  const agentChatOptions = useMemo<AgentChatOptions | null>(() => {
    if (!isReady || !config || !agentCapability) return null;
    if (!config.slug) return null;
    const slug = config.slug;
    return {
      apiBaseUrl: config.apiBaseUrl,
      appId: config.appId,
      userId: config.userId,
      accessToken: config.accessToken,
      slug,
      storagePrefix,
      capabilityName: agentCapability,
      locale,
      deviceKey: config.deviceKey,
      agentCardUrl: `${config.apiBaseUrl}/api/apps/${slug}/agent.json`,
    };
  }, [isReady, config, agentCapability, storagePrefix, locale]);

  const agentChat = useAgentChat(
    agentCapability ? agentChatOptions : null,
  );

  // Fetch personality from bootstrap for the chat FAB avatar
  const [appPersonality, setAppPersonality] = useState<Personality | null>(null);
  useEffect(() => {
    if (!isReady || !config?.slug || !config?.apiBaseUrl) return;
    let cancelled = false;
    fetch(`${config.apiBaseUrl}/api/apps/${config.slug}/bootstrap`, {
      headers: { Authorization: `Bearer ${config.accessToken}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data?.personality) return;
        // Avatar paths are relative (e.g. /avatars/trainer.png) and resolve
        // against the app's own origin in both dev and CDN-hosted modes.
        // No base URL prepending needed.
        setAppPersonality(data.personality);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [isReady, config?.slug, config?.apiBaseUrl, config?.accessToken]);

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  function handleThemeToggle() {
    const next = darkMode ? "light" : "dark";
    setDarkMode(!darkMode);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // localStorage unavailable
    }
    syncThemeToDocument(next);
  }

  function handleLocaleChange(next: SupportedLocale) {
    // Notify the app synchronously BEFORE React re-renders so the app's
    // i18n module is updated before t() calls in the next render cycle.
    if (onLocaleChangeProp) {
      onLocaleChangeProp(next);
    }
    setLocale(next);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // localStorage unavailable
    }
  }

  function handleStartLogin() {
    if (!config || loginPending) return;
    setLoginPending(true);
    try {
      const loginUrl = client.buildNexoLoginUrl();
      window.setTimeout(() => {
        window.location.assign(loginUrl);
      }, 0);
    } catch {
      setLoginPending(false);
      // buildNexoLoginUrl throws if auth_base_url not configured;
      // silently ignore in that case (guest apps without hosted auth)
    }
  }

  // -------------------------------------------------------------------------
  // Context for render-prop children
  // -------------------------------------------------------------------------

  const shellContext: NexoAppShellContext = {
    isReady,
    connectionStatus,
    connectionError: connectionErrorMsg,
    authMode,
    locale,
    darkMode,
    toggleDarkMode: handleThemeToggle,
    setLocale: handleLocaleChange,
    config,
    bootstrap,
    isWebview,
  };

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  function renderChildren() {
    if (typeof children === "function") {
      return children(shellContext);
    }
    return children;
  }

  // -------------------------------------------------------------------------
  // Skip default chrome: connection-only mode
  // -------------------------------------------------------------------------

  if (skipDefaultChrome) {
    return (
      <div
        className={`nexo-app-shell ${darkMode ? "nexo-app-shell--dark" : ""} ${className ?? ""}`}
      >
        {renderChildren()}
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  if (connectionStatus === "connecting") {
    return (
      <div
        className={`nexo-app-shell nexo-app-shell__loading ${className ?? ""}`}
      >
        <p>{labels.connecting}</p>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  if (connectionStatus === "error") {
    return (
      <div
        className={`nexo-app-shell nexo-app-shell__error ${className ?? ""}`}
      >
        <p className="nexo-app-shell__error-title">{labels.connectionError}</p>
        {connectionErrorMsg && (
          <p className="nexo-app-shell__error-detail">{connectionErrorMsg}</p>
        )}
        <p className="nexo-app-shell__error-hint">{labels.connectionErrorHint}</p>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Webview mode - bare content, no shell chrome
  // -------------------------------------------------------------------------

  if (isWebview) {
    return (
      <div
        className={`nexo-app-shell nexo-app-shell--webview ${darkMode ? "nexo-app-shell--dark" : ""} ${className ?? ""}`}
      >
        <div className="nexo-app-shell__content">{renderChildren()}</div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Standalone mode - full shell with toolbar
  // -------------------------------------------------------------------------

  const showAuthStatusCard =
    authMode !== "guest" && accessState !== null && accessState !== "access_granted";

  return (
    <div
      className={`nexo-app-shell ${darkMode ? "nexo-app-shell--dark" : ""} ${className ?? ""}`}
    >
      {/* Toolbar */}
      {!hideToolbar && (
        <div className="nexo-app-shell__toolbar">
          <div className="nexo-app-shell__toolbar-inner">
            <div className="nexo-app-shell__toolbar-left">
              <span className="nexo-app-shell__app-name">{appName}</span>
            </div>

            <div className="nexo-app-shell__toolbar-right">
              {renderToolbarRight ? (
                renderToolbarRight({
                  ...shellContext,
                  onThemeToggle: handleThemeToggle,
                  onStartLogin: handleStartLogin,
                  onLocaleChange: handleLocaleChange,
                })
              ) : (
                <>
                  {/* Theme toggle */}
                  <button
                    type="button"
                    className="nexo-theme-toggle"
                    onClick={handleThemeToggle}
                    aria-pressed={darkMode}
                    disabled={loginPending}
                  >
                    {darkMode ? <SunIcon /> : <MoonIcon />}
                  </button>

                  {/* Locale selector */}
                  {!loginPending && (
                    <LocaleDropdown locale={locale} onSelect={handleLocaleChange} />
                  )}

                  {/* Login button for guest users */}
                  {authMode === "guest" && (
                    <NexoAuthStatusCard
                      authMode={authMode}
                      accessState={accessState}
                      onStartLogin={handleStartLogin}
                      loginPending={loginPending}
                      variant="compact"
                      labels={{
                        signInLabel: labels.signInLabel,
                        accessPendingTitle: labels.accessPendingTitle,
                        accessPendingDesc: labels.accessPendingDesc,
                        inviteRequiredTitle: labels.inviteRequiredTitle,
                        inviteRequiredDesc: labels.inviteRequiredDesc,
                        inviteCodeRequiredTitle: labels.inviteCodeRequiredTitle,
                        inviteCodeRequiredDesc: labels.inviteCodeRequiredDesc,
                      }}
                    />
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Auth status cards for non-guest states with restricted access */}
      {showAuthStatusCard && (
        <NexoAuthStatusCard
          authMode={authMode}
          accessState={accessState}
          onStartLogin={null}
          variant="compact"
          labels={{
            signInLabel: labels.signInLabel,
            accessPendingTitle: labels.accessPendingTitle,
            accessPendingDesc: labels.accessPendingDesc,
            inviteRequiredTitle: labels.inviteRequiredTitle,
            inviteRequiredDesc: labels.inviteRequiredDesc,
            inviteCodeRequiredTitle: labels.inviteCodeRequiredTitle,
            inviteCodeRequiredDesc: labels.inviteCodeRequiredDesc,
          }}
        />
      )}

      {/* Main content */}
      <div className="nexo-app-shell__content">{renderChildren()}</div>

      {/* Agent chat FAB (standalone mode only, hidden in webview) */}
      {agentCapability && labels.chatFabAriaLabel && agentChatOptions && (
        <AgentChatFab
          chatOptions={agentChatOptions}
          personality={appPersonality ?? undefined}
          shellMode="standalone"
          ariaLabel={labels.chatFabAriaLabel}
          label={labels.chatFabLabel}
          avatar={chatFabAvatar}
          renderPanel={({ chatOptions: _chatOptions, personality, onClose }) => (
            <AgentChatPanel
              messages={agentChat.messages}
              suggestions={agentChat.suggestions}
              sending={agentChat.sending}
              progress={agentChat.progress}
              error={agentChat.error}
              onSendMessage={agentChat.sendMessage}
              onClearThread={agentChat.clearThread}
              personality={personality}
              title={labels.chatTitle ?? appName}
              welcomeTitle={labels.chatWelcomeTitle}
              welcomeDescription={labels.chatWelcomeDescription}
              placeholder={labels.chatPlaceholder ?? ""}
              clearLabel={labels.chatClearLabel ?? labels.chatNewLabel ?? ""}
              closeLabel={labels.chatCloseLabel ?? ""}
              onClose={onClose}
            />
          )}
        />
      )}
    </div>
  );
}
