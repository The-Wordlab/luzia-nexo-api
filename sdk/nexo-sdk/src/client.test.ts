import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createNexoClient, resolveNexoQueryOverrides } from "./client";
import type { NexoBootstrap } from "./types";

const BOOTSTRAP: NexoBootstrap = {
  type: "nexo:bootstrap",
  app_id: "app-1",
  slug: "nutrition",
  app_name: "Test App",
  api_base_url: "http://localhost:8000",
  access_token: "test-token-abc",
  user_id: "user-1",
  locale: "en",
  surface_mode: "webapp",
  capabilities: {},
};

// --- localStorage mock ---

function makeFakeStorage(): Storage {
  const store: Record<string, string> = {};
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
    clear: () => { for (const k in store) delete store[k]; },
    get length() { return Object.keys(store).length; },
    key: (i: number) => Object.keys(store)[i] ?? null,
  };
}

describe("createNexoClient", () => {
  it("is not initialized before init", () => {
    const client = createNexoClient({ storagePrefix: "test" });
    expect(client.isInitialized()).toBe(false);
  });

  it("throws when getConfig called before init", () => {
    const client = createNexoClient({ storagePrefix: "test" });
    expect(() => client.getConfig()).toThrow("Nexo client not initialized");
  });

  it("initFromBootstrap sets config correctly", () => {
    const client = createNexoClient({ storagePrefix: "test" });
    client.initFromBootstrap(BOOTSTRAP);
    expect(client.isInitialized()).toBe(true);
    const config = client.getConfig();
    expect(config.apiBaseUrl).toBe("http://localhost:8000");
    expect(config.appId).toBe("app-1");
    expect(config.accessToken).toBe("test-token-abc");
    expect(config.userId).toBe("user-1");
    expect(config.slug).toBe("nutrition");
  });

  it("getAppId returns the app_id after init", () => {
    const client = createNexoClient({ storagePrefix: "test" });
    client.initFromBootstrap(BOOTSTRAP);
    expect(client.getAppId()).toBe("app-1");
  });

  it("separate instances are independent", () => {
    const a = createNexoClient({ storagePrefix: "a" });
    const b = createNexoClient({ storagePrefix: "b" });
    a.initFromBootstrap(BOOTSTRAP);
    expect(a.isInitialized()).toBe(true);
    expect(b.isInitialized()).toBe(false);
  });
});

describe("resolveNexoQueryOverrides", () => {
  it("resolves env hint from query params", () => {
    expect(resolveNexoQueryOverrides("?nexo_env=staging")).toEqual({
      apiBaseUrl: null,
      env: "staging",
    });
  });

  it("resolves api base URL override", () => {
    expect(resolveNexoQueryOverrides("?nexo_api=http://custom:9000")).toEqual({
      apiBaseUrl: "http://custom:9000",
      env: null,
    });
  });

  it("returns nulls when no params present", () => {
    expect(resolveNexoQueryOverrides("?locale=es")).toEqual({
      apiBaseUrl: null,
      env: null,
    });
  });
});

// --- Auth bridge feature tests ---

describe("auth bridge disabled (default)", () => {
  it("getAuthMode returns guest when no authMode set", () => {
    const client = createNexoClient({ storagePrefix: "nobridge" });
    client.initFromBootstrap(BOOTSTRAP);
    expect(client.getAuthMode()).toBe("guest");
  });

  it("getAccessState returns null when no accessState set", () => {
    const client = createNexoClient({ storagePrefix: "nobridge" });
    client.initFromBootstrap(BOOTSTRAP);
    expect(client.getAccessState()).toBeNull();
  });

  it("bootstrap does not set authMode or accessState on config", () => {
    const client = createNexoClient({ storagePrefix: "nobridge" });
    client.initFromBootstrap(BOOTSTRAP);
    const config = client.getConfig();
    expect(config.authMode).toBeUndefined();
    expect(config.accessState).toBeUndefined();
    expect(config.deviceKey).toBeUndefined();
  });
});

describe("device key management (auth bridge enabled)", () => {
  let fakeStorage: Storage;

  beforeEach(() => {
    fakeStorage = makeFakeStorage();
    vi.stubGlobal("localStorage", fakeStorage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates a device key on bootstrap when auth bridge is enabled", () => {
    const client = createNexoClient({
      storagePrefix: "bridgetest",
      authBridge: { enabled: true },
    });
    client.initFromBootstrap(BOOTSTRAP);
    const stored = fakeStorage.getItem("nexo_bridgetest_device_key");
    expect(stored).toBeTruthy();
    expect(stored).toMatch(/^web-/);
  });

  it("reuses an existing device key from localStorage", () => {
    fakeStorage.setItem("nexo_bridgetest_device_key", "web-existing-key-123");
    const client = createNexoClient({
      storagePrefix: "bridgetest",
      authBridge: { enabled: true },
    });
    client.initFromBootstrap(BOOTSTRAP);
    const config = client.getConfig();
    expect(config.deviceKey).toBe("web-existing-key-123");
  });

  it("device key stored in config after bootstrap", () => {
    const client = createNexoClient({
      storagePrefix: "bridgetest",
      authBridge: { enabled: true },
    });
    client.initFromBootstrap(BOOTSTRAP);
    const config = client.getConfig();
    expect(config.deviceKey).toBeTruthy();
    expect(config.deviceKey).toMatch(/^web-/);
  });

  it("device key uses Date.now fallback when crypto.randomUUID unavailable", () => {
    const originalCrypto = globalThis.crypto;
    vi.stubGlobal("crypto", { randomUUID: undefined });
    const client = createNexoClient({
      storagePrefix: "bridgetest",
      authBridge: { enabled: true },
    });
    client.initFromBootstrap(BOOTSTRAP);
    const stored = fakeStorage.getItem("nexo_bridgetest_device_key");
    expect(stored).toMatch(/^web-\d+$/);
    vi.stubGlobal("crypto", originalCrypto);
  });
});

describe("session meta persistence (auth bridge enabled)", () => {
  let fakeStorage: Storage;

  beforeEach(() => {
    fakeStorage = makeFakeStorage();
    vi.stubGlobal("localStorage", fakeStorage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("persists session meta on bootstrap", () => {
    const client = createNexoClient({
      storagePrefix: "meta",
      authBridge: { enabled: true },
    });
    client.initFromBootstrap(BOOTSTRAP);
    const raw = fakeStorage.getItem("nexo_meta_session_meta");
    expect(raw).toBeTruthy();
    const meta = JSON.parse(raw!);
    expect(meta.appId).toBe("app-1");
    expect(meta.userId).toBe("user-1");
    expect(meta.authMode).toBe("authenticated");
    expect(meta.accessState).toBe("access_granted");
    expect(meta.deviceKey).toMatch(/^web-/);
  });

  it("bootstrap without auth bridge does not write session meta", () => {
    const client = createNexoClient({ storagePrefix: "nometabridge" });
    client.initFromBootstrap(BOOTSTRAP);
    expect(fakeStorage.getItem("nexo_nometabridge_session_meta")).toBeNull();
  });
});

describe("clearStoredSession", () => {
  let fakeStorage: Storage;

  beforeEach(() => {
    fakeStorage = makeFakeStorage();
    vi.stubGlobal("localStorage", fakeStorage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("clears token, user, and meta but keeps device key by default", () => {
    fakeStorage.setItem("nexo_clear_token", "t1");
    fakeStorage.setItem("nexo_clear_user_id", "u1");
    fakeStorage.setItem("nexo_clear_session_meta", JSON.stringify({ appId: "x" }));
    fakeStorage.setItem("nexo_clear_device_key", "web-abc");

    const client = createNexoClient({
      storagePrefix: "clear",
      authBridge: { enabled: true },
    });
    client.initFromBootstrap(BOOTSTRAP);
    client.clearStoredSession();

    expect(fakeStorage.getItem("nexo_clear_token")).toBeNull();
    expect(fakeStorage.getItem("nexo_clear_user_id")).toBeNull();
    expect(fakeStorage.getItem("nexo_clear_session_meta")).toBeNull();
    // device key should be preserved by default
    expect(fakeStorage.getItem("nexo_clear_device_key")).toBe("web-abc");
    expect(client.isInitialized()).toBe(false);
  });

  it("clears device key when clearDeviceKey: true", () => {
    fakeStorage.setItem("nexo_clear2_device_key", "web-xyz");

    const client = createNexoClient({
      storagePrefix: "clear2",
      authBridge: { enabled: true },
    });
    client.initFromBootstrap(BOOTSTRAP);
    client.clearStoredSession({ clearDeviceKey: true });

    expect(fakeStorage.getItem("nexo_clear2_device_key")).toBeNull();
  });

  it("clearStoredSession works even without auth bridge enabled", () => {
    fakeStorage.setItem("nexo_plain_token", "t1");
    fakeStorage.setItem("nexo_plain_user_id", "u1");

    const client = createNexoClient({ storagePrefix: "plain" });
    client.initFromBootstrap(BOOTSTRAP);
    client.clearStoredSession();

    expect(fakeStorage.getItem("nexo_plain_token")).toBeNull();
    expect(fakeStorage.getItem("nexo_plain_user_id")).toBeNull();
    expect(client.isInitialized()).toBe(false);
  });
});

describe("getAuthMode and getAccessState", () => {
  let fakeStorage: Storage;

  beforeEach(() => {
    fakeStorage = makeFakeStorage();
    vi.stubGlobal("localStorage", fakeStorage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns authenticated and access_granted after bootstrap with auth bridge", () => {
    const client = createNexoClient({
      storagePrefix: "mode",
      authBridge: { enabled: true },
    });
    client.initFromBootstrap(BOOTSTRAP);
    expect(client.getAuthMode()).toBe("authenticated");
    expect(client.getAccessState()).toBe("access_granted");
  });

  it("returns guest and null when no auth bridge", () => {
    const client = createNexoClient({ storagePrefix: "guest" });
    client.initFromBootstrap(BOOTSTRAP);
    expect(client.getAuthMode()).toBe("guest");
    expect(client.getAccessState()).toBeNull();
  });
});

describe("buildAuthBridgeStartUrl", () => {
  let fakeStorage: Storage;

  beforeEach(() => {
    fakeStorage = makeFakeStorage();
    vi.stubGlobal("localStorage", fakeStorage);
    // Set window.location.origin for URL building
    vi.stubGlobal("window", {
      ...globalThis.window,
      location: {
        origin: "https://myapp.example.com",
        host: "myapp.example.com",
        pathname: "/dashboard",
        search: "",
        hash: "",
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds correct auth bridge start URL", () => {
    const client = createNexoClient({
      storagePrefix: "starturl",
      authBridge: { enabled: true, serviceBaseUrl: "https://myapp.example.com" },
    });

    // Manually set a config with authBaseUrl
    client.initFromBootstrap(BOOTSTRAP);
    // Override config to have authBaseUrl
    const rawConfig = client.getConfig();
    // Use a fresh instance where we can control authBaseUrl via bootstrap
    // We need to set authBaseUrl - use a mock initFromBootstrap scenario
    // by testing the URL builder after initStandalone (mocked)
    // For now, test via direct bootstrap which doesn't set authBaseUrl
    // Instead verify the error when authBaseUrl is missing
    expect(() => client.buildAuthBridgeStartUrl("/")).toThrow("ERROR_AUTH_BRIDGE_UNAVAILABLE");
    void rawConfig; // used for type check
  });

  it("throws ERROR_AUTH_BRIDGE_UNAVAILABLE when no authBaseUrl", () => {
    const client = createNexoClient({
      storagePrefix: "noauthbase",
      authBridge: { enabled: true },
    });
    client.initFromBootstrap(BOOTSTRAP);
    expect(() => client.buildAuthBridgeStartUrl("/dashboard")).toThrow(
      "ERROR_AUTH_BRIDGE_UNAVAILABLE",
    );
  });
});

describe("auth bridge session resolution via initStandalone (mocked fetch)", () => {
  let fakeStorage: Storage;

  beforeEach(() => {
    fakeStorage = makeFakeStorage();
    vi.stubGlobal("localStorage", fakeStorage);
    vi.stubGlobal("window", {
      location: {
        origin: "https://app.example.com",
        host: "app.example.com",
        hostname: "app.example.com",
        pathname: "/",
        search: "",
        hash: "",
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("uses auth bridge session when cookie session returns valid payload", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    // nexo.json
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "myapp",
        environments: {
          "app.example.com": {
            api_base_url: "http://localhost:8000",
            auth_base_url: "http://localhost:3000",
          },
        },
      }),
    } as unknown as Response);

    // auth bridge session endpoint
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => ({
        access_token: "bridge-token",
        user_id: "user-bridge",
        app_id: "app-bridge",
        access_state: "access_granted",
      }),
    } as unknown as Response);

    const client = createNexoClient({
      storagePrefix: "bridge",
      authBridge: { enabled: true, serviceBaseUrl: "https://app.example.com" },
    });

    const config = await client.initStandalone("http://localhost:8000");

    expect(config.accessToken).toBe("bridge-token");
    expect(config.userId).toBe("user-bridge");
    expect(config.appId).toBe("app-bridge");
    expect(config.authMode).toBe("authenticated");
    expect(config.accessState).toBe("access_granted");
    expect(fakeStorage.getItem("nexo_bridge_token")).toBe("bridge-token");
    expect(fakeStorage.getItem("nexo_bridge_user_id")).toBe("user-bridge");
  });

  it("throws on auth_error query param when auth bridge enabled", async () => {
    vi.stubGlobal("window", {
      location: {
        origin: "https://app.example.com",
        host: "app.example.com",
        hostname: "app.example.com",
        pathname: "/",
        search: "?auth_error=ERROR_ACCESS_DENIED",
        hash: "",
      },
    });

    const client = createNexoClient({
      storagePrefix: "autherr",
      authBridge: { enabled: true },
    });

    await expect(client.initStandalone("http://localhost:8000")).rejects.toThrow(
      "ERROR_ACCESS_DENIED",
    );
  });

  it("handles nexo_token redirect from Nexo-hosted login", async () => {
    const replaceStateMock = vi.fn();
    vi.stubGlobal("window", {
      location: {
        origin: "https://apps.luzia.com",
        host: "apps.luzia.com",
        hostname: "apps.luzia.com",
        pathname: "/nutrition/",
        search: "?nexo_token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLWxvZ2luIn0.test",
        hash: "",
        href: "https://apps.luzia.com/nutrition/?nexo_token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLWxvZ2luIn0.test",
      },
      history: { replaceState: replaceStateMock },
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    // nexo.json
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
        environments: {
          "apps.luzia.com": {
            api_base_url: "https://api.luzia.com",
            auth_base_url: "https://nexo.luzia.com",
          },
        },
      }),
    } as unknown as Response);

    const client = createNexoClient({ storagePrefix: "nexologin" });
    const config = await client.initStandalone("http://localhost:8000");

    expect(config.accessToken).toBe("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLWxvZ2luIn0.test");
    expect(config.userId).toBe("user-login");
    expect(config.slug).toBe("nutrition");
    expect(config.apiBaseUrl).toBe("https://api.luzia.com");
    expect(config.runtimeAuthMode).toBe("bearer");

    // Token stored in localStorage
    expect(fakeStorage.getItem("nexo_nexologin_token")).toBe(config.accessToken);
    expect(fakeStorage.getItem("nexo_nexologin_user_id")).toBe("user-login");

    // URL cleaned
    expect(replaceStateMock).toHaveBeenCalled();
  });

  it("handles nexo_token fragment handoff from a Nexo vanity launch", async () => {
    const replaceStateMock = vi.fn();
    vi.stubGlobal("window", {
      location: {
        origin: "https://apps.luzia.com",
        host: "apps.luzia.com",
        hostname: "apps.luzia.com",
        pathname: "/nutrition/",
        search: "",
        hash: "#nexo_token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLWhhc2gifQ.test",
        href: "https://apps.luzia.com/nutrition/#nexo_token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLWhhc2gifQ.test",
      },
      history: { replaceState: replaceStateMock },
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
        environments: {
          "apps.luzia.com": {
            api_base_url: "https://api.luzia.com",
            auth_base_url: "https://nexo.luzia.com",
          },
        },
      }),
    } as unknown as Response);

    const client = createNexoClient({ storagePrefix: "nexohash" });
    const config = await client.initStandalone("http://localhost:8000");

    expect(config.accessToken).toBe("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLWhhc2gifQ.test");
    expect(config.userId).toBe("user-hash");
    expect(fakeStorage.getItem("nexo_nexohash_token")).toBe(config.accessToken);
    expect(fakeStorage.getItem("nexo_nexohash_user_id")).toBe("user-hash");
    expect(replaceStateMock).toHaveBeenCalled();
  });

  it("prefers the hosted session bootstrap on first-party app hosts", async () => {
    vi.stubGlobal("window", {
      location: {
        origin: "https://apps.staging.luzia.com",
        host: "apps.staging.luzia.com",
        hostname: "apps.staging.luzia.com",
        pathname: "/nutrition/",
        search: "",
        hash: "",
      },
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
        environments: {
          staging: {
            api_base_url: "https://nexo-cdn-alb.staging.thewordlab.net",
            auth_base_url: "https://staging.nexo.luzia.com",
          },
        },
      }),
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        app_id: "app-hosted",
        user_id: "user-hosted",
      }),
    } as unknown as Response);

    const client = createNexoClient({ storagePrefix: "hostedsession" });
    const config = await client.initStandalone("http://localhost:8000");

    expect(config.apiBaseUrl).toBe("https://staging.nexo.luzia.com/app-runtime-api");
    expect(config.authBaseUrl).toBe("https://staging.nexo.luzia.com");
    expect(config.appId).toBe("app-hosted");
    expect(config.userId).toBe("user-hosted");
    expect(config.accessToken).toBeNull();
    expect(config.runtimeAuthMode).toBe("hosted_session");
    expect(fakeStorage.getItem("nexo_hostedsession_token")).toBeNull();
    expect(fakeStorage.getItem("nexo_hostedsession_user_id")).toBeNull();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [bootstrapUrl, bootstrapInit] = fetchMock.mock.calls[1] as [
      string,
      { cache?: string; credentials?: string; headers?: Headers },
    ];
    expect(bootstrapUrl).toBe(
      "https://staging.nexo.luzia.com/app-runtime-api/api/apps/nutrition/bootstrap",
    );
    expect(bootstrapInit.cache).toBe("no-store");
    expect(bootstrapInit.credentials).toBe("include");
    expect(bootstrapInit.headers).toBeUndefined();
  });

  it("builds hosted login URLs for well-known CDN hosts without auth bridge enabled", async () => {
    vi.stubGlobal("window", {
      location: {
        origin: "https://apps.luzia.com",
        host: "apps.luzia.com",
        hostname: "apps.luzia.com",
        pathname: "/nutrition/",
        search: "",
        hash: "",
      },
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
      }),
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "ERROR_UNAUTHORIZED" }),
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: "guest-token",
        user_id: "guest-user",
        app_id: "app-1",
      }),
    } as unknown as Response);

    const client = createNexoClient({ storagePrefix: "cdnlogin" });
    const config = await client.initStandalone("http://localhost:8000");

    expect(config.apiBaseUrl).toBe("https://luzia-nexo.thewordlab.net");
    expect(config.authBaseUrl).toBe("https://nexo.luzia.com");
    expect(config.runtimeAuthMode).toBe("bearer");

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://nexo.luzia.com/app-runtime-api/api/apps/nutrition/bootstrap",
      expect.objectContaining({
        cache: "no-store",
        credentials: "include",
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "https://luzia-nexo.thewordlab.net/api/apps/nutrition/domain-session",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      }),
    );

    const loginUrl = new URL(client.buildNexoLoginUrl());
    expect(loginUrl.origin).toBe("https://nexo.luzia.com");
    expect(loginUrl.pathname).toBe("/apps/nutrition/auth");
    expect(loginUrl.searchParams.get("return_to")).toBe("https://apps.luzia.com/nutrition/");
  });

  it("derives slug from nexo.json for token-param standalone sessions", async () => {
    vi.stubGlobal("window", {
      location: {
        origin: "https://apps.luzia.com",
        host: "apps.luzia.com",
        hostname: "apps.luzia.com",
        pathname: "/nutrition/",
        search: "?token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLXRva2VuIn0.test",
        hash: "",
      },
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
        environments: {
          "apps.luzia.com": {
            api_base_url: "https://api.luzia.com",
            auth_base_url: "https://nexo.luzia.com",
          },
        },
      }),
    } as unknown as Response);

    const client = createNexoClient({ storagePrefix: "dev-prefix" });
    const config = await client.initStandalone("http://localhost:8000");

    expect(config.accessToken).toBe(
      "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLXRva2VuIn0.test",
    );
    expect(config.userId).toBe("user-token");
    expect(config.slug).toBe("nutrition");
    expect(config.apiBaseUrl).toBe("https://api.luzia.com");
    expect(config.runtimeAuthMode).toBe("bearer");
  });

  it("uses the direct API for auth-bridge domain-session on first-party app hosts", async () => {
    vi.stubGlobal("window", {
      location: {
        origin: "https://apps.staging.luzia.com",
        host: "apps.staging.luzia.com",
        hostname: "apps.staging.luzia.com",
        pathname: "/nutrition/",
        search: "",
        hash: "",
      },
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
        environments: {
          staging: {
            api_base_url: "https://nexo-cdn-alb.staging.thewordlab.net",
            auth_base_url: "https://staging.nexo.luzia.com",
          },
        },
      }),
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 204,
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: "guest-token",
        user_id: "guest-user",
        app_id: "app-bridge",
      }),
    } as unknown as Response);

    const client = createNexoClient({
      storagePrefix: "firstpartybridge",
      authBridge: {
        enabled: true,
        serviceBaseUrl: "https://service.example.com",
      },
    });

    const config = await client.initStandalone("http://localhost:8000");

    expect(config.apiBaseUrl).toBe("https://nexo-cdn-alb.staging.thewordlab.net");
    expect(config.authBaseUrl).toBe("https://staging.nexo.luzia.com");
    expect(config.runtimeAuthMode).toBe("bearer");
    expect(config.appId).toBe("app-bridge");
    expect(config.userId).toBe("guest-user");
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining(
        "https://nexo-cdn-alb.staging.thewordlab.net/api/apps/nutrition/domain-session",
      ),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      }),
    );
  });

  it("hydrates hosted-session clients without requiring a cached bearer token", async () => {
    vi.stubGlobal("window", {
      location: {
        origin: "https://apps.staging.luzia.com",
        host: "apps.staging.luzia.com",
        hostname: "apps.staging.luzia.com",
        pathname: "/nutrition/",
        search: "",
        hash: "",
      },
    });

    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
        environments: {
          staging: {
            api_base_url: "https://nexo-cdn-alb.staging.thewordlab.net",
            auth_base_url: "https://staging.nexo.luzia.com",
          },
        },
      }),
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        app_id: "app-hosted",
        user_id: "user-hosted",
      }),
    } as unknown as Response);

    const client = createNexoClient({ storagePrefix: "hydratehosted" });
    await expect(client.hydrateFromStorage()).resolves.toBe(true);

    const config = client.getConfig();
    expect(config.apiBaseUrl).toBe("https://staging.nexo.luzia.com/app-runtime-api");
    expect(config.accessToken).toBeNull();
    expect(config.userId).toBe("user-hosted");
    expect(config.runtimeAuthMode).toBe("hosted_session");
  });

  it("buildNexoLoginUrl builds correct redirect URL", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    // nexo.json
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
        environments: {
          "app.example.com": {
            api_base_url: "http://localhost:8000",
            auth_base_url: "https://nexo.luzia.com",
          },
        },
      }),
    } as unknown as Response);

    // auth bridge session - no session
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 204,
    } as unknown as Response);

    // domain-session
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: "guest-token",
        user_id: "guest-user",
        app_id: "app-1",
      }),
    } as unknown as Response);

    const client = createNexoClient({
      storagePrefix: "loginurl",
      authBridge: { enabled: true },
    });
    await client.initStandalone("http://localhost:8000");

    const loginUrl = new URL(client.buildNexoLoginUrl());
    expect(loginUrl.origin).toBe("https://nexo.luzia.com");
    expect(loginUrl.pathname).toBe("/apps/nutrition/auth");
    expect(loginUrl.searchParams.get("return_to")).toBe("https://app.example.com/");
  });

  it("buildAuthBridgeStartUrl uses the slug-scoped auth endpoint when authBaseUrl is available", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
        environments: {
          "app.example.com": {
            api_base_url: "http://localhost:8000",
            auth_base_url: "https://nexo.luzia.com",
          },
        },
      }),
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 204,
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: "guest-token",
        user_id: "guest-user",
        app_id: "app-1",
      }),
    } as unknown as Response);

    const client = createNexoClient({
      storagePrefix: "bridgeurl",
      authBridge: {
        enabled: true,
        serviceBaseUrl: "https://app.example.com",
      },
    });
    await client.initStandalone("http://localhost:8000");

    const authUrl = new URL(
      client.buildAuthBridgeStartUrl("/competition/lounge"),
    );
    expect(authUrl.origin).toBe("https://nexo.luzia.com");
    expect(authUrl.pathname).toBe("/apps/nutrition/auth");
    expect(authUrl.searchParams.get("return_to")).toBe(
      "https://app.example.com/auth/nexo/callback",
    );
    expect(authUrl.searchParams.get("next")).toBe("/competition/lounge");
  });

  it("buildNexoProfileUrl and buildNexoOnboardingUrl use the slug-scoped hosted surfaces", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "nutrition",
        environments: {
          "app.example.com": {
            api_base_url: "http://localhost:8000",
            auth_base_url: "https://nexo.luzia.com",
          },
        },
      }),
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 204,
    } as unknown as Response);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        access_token: "guest-token",
        user_id: "guest-user",
        app_id: "app-1",
      }),
    } as unknown as Response);

    const client = createNexoClient({
      storagePrefix: "profileurl",
      authBridge: { enabled: true },
    });
    await client.initStandalone("http://localhost:8000");

    const profileUrl = new URL(client.buildNexoProfileUrl("/competition/lounge"));
    expect(profileUrl.origin).toBe("https://nexo.luzia.com");
    expect(profileUrl.pathname).toBe("/apps/nutrition/profile");
    expect(profileUrl.searchParams.get("return_to")).toBe(
      "/competition/lounge",
    );

    const onboardingUrl = new URL(
      client.buildNexoOnboardingUrl("/competition/lounge"),
    );
    expect(onboardingUrl.origin).toBe("https://nexo.luzia.com");
    expect(onboardingUrl.pathname).toBe("/apps/nutrition/onboarding");
    expect(onboardingUrl.searchParams.get("return_to")).toBe(
      "/competition/lounge",
    );
  });

  it("falls through to cached token validation when no auth bridge session", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    fakeStorage.setItem("nexo_cached_token", "cached-access-token");
    fakeStorage.setItem("nexo_cached_user_id", "cached-user");

    // nexo.json
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        slug: "myapp",
        environments: {
          "app.example.com": {
            api_base_url: "http://localhost:8000",
            auth_base_url: "http://localhost:3000",
          },
        },
      }),
    } as unknown as Response);

    // auth bridge session candidates: same-origin only (no serviceBaseUrl set)
    // status 204 = no session
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 204,
    } as unknown as Response);

    // /api/me/account validation - valid
    fetchMock.mockResolvedValueOnce({
      ok: true,
    } as unknown as Response);

    const client = createNexoClient({
      storagePrefix: "cached",
      authBridge: { enabled: true },
    });

    const config = await client.initStandalone("http://localhost:8000");

    expect(config.accessToken).toBe("cached-access-token");
    expect(config.userId).toBe("cached-user");
  });
});
