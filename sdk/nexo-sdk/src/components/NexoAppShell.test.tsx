/**
 * Tests for NexoAppShell component.
 *
 * TDD: these tests were written before the implementation.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { NexoAppShell } from "./NexoAppShell";
import type { NexoAppShellLabels } from "./NexoAppShell";
import * as clientModule from "../client";
import * as bootstrapModule from "../useNexoBootstrap";

// ---------------------------------------------------------------------------
// We set up mocks at the top level before importing the component.
// ---------------------------------------------------------------------------

// Mock createNexoClient
vi.mock("../client", () => {
  function makeClient(opts?: {
    rejectInit?: boolean;
    neverResolve?: boolean;
    authMode?: string;
    accessState?: string | null;
    loginUrl?: string;
  }) {
    const resolvedConfig = {
      apiBaseUrl: "http://localhost:8000",
      appId: "app-1",
      slug: "test",
      accessToken: "tok",
      userId: "user-1",
      authMode: opts?.authMode ?? "guest",
      accessState: opts?.accessState ?? null,
    };

    let initStandaloneFn: () => Promise<typeof resolvedConfig>;
    if (opts?.neverResolve) {
      initStandaloneFn = () => new Promise(() => {});
    } else if (opts?.rejectInit) {
      initStandaloneFn = () => Promise.reject(new Error("Connection failed"));
    } else {
      initStandaloneFn = () => Promise.resolve(resolvedConfig);
    }

    return {
      initFromBootstrap: vi.fn(),
      initStandalone: vi.fn(initStandaloneFn),
      getConfig: vi.fn().mockReturnValue(resolvedConfig),
      isInitialized: vi.fn().mockReturnValue(true),
      getAuthMode: vi.fn().mockReturnValue(opts?.authMode ?? "guest"),
      getAccessState: vi.fn().mockReturnValue(opts?.accessState ?? null),
      buildNexoLoginUrl: vi.fn().mockReturnValue(
        opts?.loginUrl ??
          "http://nexo.example.com/apps/test/auth?return_to=http%3A%2F%2Flocalhost%3A5173%2F",
      ),
      buildNexoProfileUrl: vi.fn(),
      buildNexoOnboardingUrl: vi.fn(),
      clearStoredSession: vi.fn(),
      buildAuthBridgeStartUrl: vi.fn(),
      prepareAuthBridgeStart: vi.fn(),
      get: vi.fn(),
      post: vi.fn(),
      patch: vi.fn(),
      del: vi.fn(),
    };
  }

  // Default factory - returns a connected guest client
  const createNexoClientMock = vi.fn(() => makeClient());

  // Attach makeClient so tests can call it
  (createNexoClientMock as unknown as { _make: typeof makeClient })._make =
    makeClient;

  return {
    createNexoClient: createNexoClientMock,
    resolveNexoQueryOverrides: vi.fn(() => ({ apiBaseUrl: null, env: null })),
  };
});

// Mock useNexoBootstrap - default: no bootstrap (standalone mode)
vi.mock("../useNexoBootstrap", () => ({
  useNexoBootstrap: vi.fn(() => null),
}));

// Mock useAgentChat to avoid async side-effects in tests
vi.mock("../useAgentChat", () => ({
  useAgentChat: vi.fn(() => ({
    messages: [],
    sending: false,
    progress: null,
    error: null,
    suggestions: [],
    sendMessage: vi.fn(),
    clearThread: vi.fn(),
  })),
}));

// ---------------------------------------------------------------------------
// localStorage mock
// ---------------------------------------------------------------------------

function makeFakeStorage(): Storage {
  const store: Record<string, string> = {};
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      for (const k in store) delete store[k];
    },
    get length() {
      return Object.keys(store).length;
    },
    key: (i: number) => Object.keys(store)[i] ?? null,
  };
}

// ---------------------------------------------------------------------------
// Labels fixture
// ---------------------------------------------------------------------------

const LABELS: NexoAppShellLabels = {
  signInLabel: "Sign in with Luzia",
  connecting: "Connecting...",
  connectionError: "Connection error",
  connectionErrorHint: "Please try again later",
  accessPendingTitle: "Access pending",
  accessPendingDesc: "Your request is being reviewed",
  inviteRequiredTitle: "Invite required",
  inviteRequiredDesc: "You need an invite to access this app",
  inviteCodeRequiredTitle: "Invite code required",
  inviteCodeRequiredDesc: "Enter your invite code to continue",
  chatFabAriaLabel: "Chat",
  chatPlaceholder: "Ask a question...",
  chatNewLabel: "New",
  chatCloseLabel: "Close",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("NexoAppShell", () => {
  let fakeStorage: Storage;

  beforeEach(() => {
    fakeStorage = makeFakeStorage();
    vi.stubGlobal("localStorage", fakeStorage);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => null,
      }),
    );
    vi.stubGlobal("location", {
      search: "",
      href: "http://localhost:5173/",
      origin: "http://localhost:5173",
      pathname: "/",
      assign: vi.fn(),
    });
    // Reset mock to default (connected guest client)
    vi.mocked(clientModule.createNexoClient).mockReset();
    vi.mocked(clientModule.createNexoClient).mockImplementation(() => {
      const { _make } = vi.mocked(clientModule.createNexoClient) as unknown as {
        _make: (o?: unknown) => ReturnType<typeof clientModule.createNexoClient>;
      };
      return _make ? _make() : (null as never);
    });
    vi.mocked(bootstrapModule.useNexoBootstrap).mockReturnValue(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Helper to create a client with specific behavior
  // -------------------------------------------------------------------------

  function useConnectedClient(
    opts?: Parameters<typeof makeConnectedClient>[0],
  ) {
    vi.mocked(clientModule.createNexoClient).mockImplementation(
      () => makeConnectedClient(opts),
    );
  }

  function makeConnectedClient(opts?: {
    authMode?: string;
    accessState?: string | null;
    loginUrl?: string;
    slug?: string;
  }) {
    const resolvedConfig = {
      apiBaseUrl: "http://localhost:8000",
      appId: "app-1",
      slug: opts?.slug ?? "test",
      accessToken: "tok",
      userId: "user-1",
      authMode: opts?.authMode ?? "guest",
      accessState: opts?.accessState ?? null,
    };
    return {
      initFromBootstrap: vi.fn(),
      initStandalone: vi.fn().mockResolvedValue(resolvedConfig),
      getConfig: vi.fn().mockReturnValue(resolvedConfig),
      isInitialized: vi.fn().mockReturnValue(true),
      getAuthMode: vi.fn().mockReturnValue(opts?.authMode ?? "guest"),
      getAccessState: vi.fn().mockReturnValue(opts?.accessState ?? null),
      buildNexoLoginUrl: vi.fn().mockReturnValue(
        opts?.loginUrl ??
          "http://nexo.example.com/apps/test/auth?return_to=http%3A%2F%2Flocalhost%3A5173%2F",
      ),
      buildNexoProfileUrl: vi.fn(),
      buildNexoOnboardingUrl: vi.fn(),
      clearStoredSession: vi.fn(),
      buildAuthBridgeStartUrl: vi.fn(),
      prepareAuthBridgeStart: vi.fn(),
      get: vi.fn(),
      post: vi.fn(),
      patch: vi.fn(),
      del: vi.fn(),
    } as ReturnType<typeof clientModule.createNexoClient>;
  }

  function makeLoadingClient() {
    const base = makeConnectedClient();
    return {
      ...base,
      initStandalone: vi.fn(() => new Promise<never>(() => {})),
    } as ReturnType<typeof clientModule.createNexoClient>;
  }

  function makeErrorClient() {
    const base = makeConnectedClient();
    return {
      ...base,
      initStandalone: vi
        .fn()
        .mockRejectedValue(new Error("Connection failed")),
    } as ReturnType<typeof clientModule.createNexoClient>;
  }

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("shows loading state during connection setup", () => {
    vi.mocked(clientModule.createNexoClient).mockReturnValue(
      makeLoadingClient(),
    );

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div data-testid="app-content">Hello</div>
      </NexoAppShell>,
    );

    expect(screen.getByText("Connecting...")).toBeInTheDocument();
    expect(screen.queryByTestId("app-content")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Connected - renders children
  // -------------------------------------------------------------------------

  it("renders children when connected", async () => {
    useConnectedClient();

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div data-testid="app-content">Hello</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("app-content")).toBeInTheDocument();
    });
  });

  it("renders children via render-prop when connected", async () => {
    useConnectedClient();

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        {(ctx) => (
          <div data-testid="render-prop-child">
            {ctx.isReady ? "ready" : "not-ready"}
          </div>
        )}
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("render-prop-child")).toHaveTextContent(
        "ready",
      );
    });
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("shows error state on connection failure", async () => {
    vi.mocked(clientModule.createNexoClient).mockReturnValue(
      makeErrorClient(),
    );

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div data-testid="app-content">Hello</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(screen.getByText("Connection error")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("app-content")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Toolbar in standalone mode
  // -------------------------------------------------------------------------

  it("shows toolbar in standalone mode", async () => {
    useConnectedClient();

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div>content</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(screen.getByText("Test App")).toBeInTheDocument();
    });

    expect(
      document.querySelector(".nexo-app-shell__toolbar"),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Webview mode - hides toolbar
  // -------------------------------------------------------------------------

  it("hides toolbar in webview mode via query param", async () => {
    vi.stubGlobal("location", {
      search: "?webview=1",
      href: "http://localhost:5173/?webview=1",
      origin: "http://localhost:5173",
      pathname: "/",
      assign: vi.fn(),
    });
    useConnectedClient();

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div data-testid="app-content">Hello</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("app-content")).toBeInTheDocument();
    });

    expect(
      document.querySelector(".nexo-app-shell__toolbar"),
    ).not.toBeInTheDocument();
  });

  it("hides toolbar when bootstrap is present (webview mode)", async () => {
    vi.mocked(bootstrapModule.useNexoBootstrap).mockReturnValue({
      type: "nexo:bootstrap",
      app_id: "app-1",
      slug: "test",
      app_name: "Test App",
      api_base_url: "http://localhost:8000",
      access_token: "tok",
      user_id: "user-1",
      locale: "en",
      surface_mode: "webapp",
      capabilities: {},
    });
    useConnectedClient();

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div data-testid="app-content">Hello</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("app-content")).toBeInTheDocument();
    });

    expect(
      document.querySelector(".nexo-app-shell__toolbar"),
    ).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Theme toggle
  // -------------------------------------------------------------------------

  it("theme toggle persists to localStorage", async () => {
    useConnectedClient();

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div>content</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(
        document.querySelector(".nexo-theme-toggle"),
      ).toBeInTheDocument();
    });

    fireEvent.click(document.querySelector(".nexo-theme-toggle")!);

    // Started as light (default) -> now dark
    expect(fakeStorage.getItem("nexo_theme")).toBe("dark");
  });

  it("theme toggle switches back to light mode", async () => {
    // Pre-seed dark mode in localStorage
    fakeStorage.setItem("nexo_theme", "dark");
    useConnectedClient();

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div>content</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(
        document.querySelector(".nexo-theme-toggle"),
      ).toBeInTheDocument();
    });

    // Initial state is dark (from localStorage), clicking toggles to light
    fireEvent.click(document.querySelector(".nexo-theme-toggle")!);

    expect(fakeStorage.getItem("nexo_theme")).toBe("light");
  });

  // -------------------------------------------------------------------------
  // Locale selector
  // -------------------------------------------------------------------------

  it("locale selector persists to localStorage", async () => {
    useConnectedClient();

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div>content</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(
        document.querySelector(".nexo-locale-trigger"),
      ).toBeInTheDocument();
    });

    // Open the dropdown
    fireEvent.click(document.querySelector(".nexo-locale-trigger")!);

    // Select Spanish (second option)
    const esOption = document.querySelector(".nexo-locale-option:nth-child(2)");
    expect(esOption).toBeInTheDocument();
    fireEvent.click(esOption!);

    expect(fakeStorage.getItem("nexo_locale")).toBe("es");
  });

  // -------------------------------------------------------------------------
  // Login button calls buildNexoLoginUrl and redirects
  // -------------------------------------------------------------------------

  it("login button calls buildNexoLoginUrl and redirects", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", {
      search: "",
      href: "http://localhost:5173/",
      origin: "http://localhost:5173",
      pathname: "/",
      assign,
    });
    useConnectedClient({
      loginUrl:
        "http://nexo.example.com/apps/test/auth?return_to=http%3A%2F%2Flocalhost%3A5173%2F",
    });

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        <div>content</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("nexo-auth-entry-button"),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("nexo-auth-entry-button"));

    expect(screen.getByTestId("nexo-auth-entry-button")).toBeDisabled();
    expect(screen.getByTestId("nexo-auth-entry-button")).toHaveAttribute(
      "aria-busy",
      "true",
    );

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(
        "http://nexo.example.com/apps/test/auth?return_to=http%3A%2F%2Flocalhost%3A5173%2F",
      );
    });
  });

  it("does not render agent chat when the resolved config has no slug", async () => {
    useConnectedClient({ slug: "" });

    render(
      <NexoAppShell
        appName="Test App"
        storagePrefix="not-a-slug"
        agentCapability="nutrition.ask_expert"
        labels={LABELS}
      >
        <div data-testid="app-content">Hello</div>
      </NexoAppShell>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("app-content")).toBeInTheDocument(),
    );

    expect(screen.queryByLabelText("Chat")).not.toBeInTheDocument();
  });

  it("exposes the resolved agent appearance from bootstrap to render-prop children", async () => {
    useConnectedClient();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        personality: {
          id: "pers-1",
          slug: "trainer",
          name: "Trainer",
          greeting: "Hello",
          suggestions: [],
          assets: { avatarLight: "/avatars/trainer.png" },
          brand: {},
        },
        agent_appearance: {
          displayName: "Elias",
          avatarLight: "/avatars/elias-bra.png",
          variantKey: "team-bra",
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <NexoAppShell appName="Test App" storagePrefix="test" labels={LABELS}>
        {(ctx) => (
          <div data-testid="resolved-appearance">
            {ctx.agentAppearance?.displayName ?? "none"}|
            {ctx.agentAppearance?.variantKey ?? "none"}|
            {ctx.personality?.name ?? "none"}
          </div>
        )}
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("resolved-appearance")).toHaveTextContent(
        "Elias|team-bra|Trainer",
      );
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/apps/test/bootstrap",
      { headers: { Authorization: "Bearer tok" } },
    );
  });

  // -------------------------------------------------------------------------
  // CSS class names
  // -------------------------------------------------------------------------

  it("applies outer container class", async () => {
    useConnectedClient();

    render(
      <NexoAppShell
        appName="Test App"
        storagePrefix="test"
        labels={LABELS}
        className="my-custom-class"
      >
        <div>content</div>
      </NexoAppShell>,
    );

    await waitFor(() => {
      expect(screen.getByText("Test App")).toBeInTheDocument();
    });

    expect(
      document.querySelector(".nexo-app-shell.my-custom-class"),
    ).toBeInTheDocument();
  });
});
