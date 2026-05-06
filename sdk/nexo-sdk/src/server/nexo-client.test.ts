import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NexoServerClient, NexoRequestError } from "./nexo-client";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    text: () => Promise.resolve(""),
    json: () => Promise.resolve({}),
    ...response,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("NexoServerClient", () => {
  let originalFetch: typeof global.fetch;

  beforeEach(() => {
    originalFetch = global.fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  // ---- constructor ----

  describe("constructor", () => {
    it("stores apiUrl from config", () => {
      const client = new NexoServerClient({ apiUrl: "http://nexo.example.com" });
      // Verify via a method that uses apiUrl - authenticate will call the right URL
      global.fetch = mockFetch({
        json: () => Promise.resolve({ access_token: "tok" }),
      });
      return expect(client.authenticate("dev-key")).resolves.toBeUndefined();
    });

    it("starts with a pre-authenticated token when bearerToken is provided", async () => {
      const fetch = mockFetch({ json: () => Promise.resolve([]) });
      global.fetch = fetch;

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        bearerToken: "pre-auth-token",
      });

      await client.listMicroApps();

      // Should NOT have called authenticate (key-exchange)
      const calls = fetch.mock.calls as [string, RequestInit][];
      expect(calls).toHaveLength(1);
      expect(calls[0][0]).not.toContain("key-exchange");
      expect(calls[0][1].headers).toMatchObject({
        Authorization: "Bearer pre-auth-token",
      });
    });
  });

  // ---- authenticate ----

  describe("authenticate()", () => {
    it("calls the key-exchange endpoint with the provided key", async () => {
      const fetch = mockFetch({
        json: () => Promise.resolve({ access_token: "fresh-token" }),
      });
      global.fetch = fetch;

      const client = new NexoServerClient({ apiUrl: "http://nexo.example.com" });
      await client.authenticate("my-dev-key");

      expect(fetch).toHaveBeenCalledOnce();
      const [url, init] = (fetch.mock.calls as [string, RequestInit][])[0];
      expect(url).toBe("http://nexo.example.com/api/auth/key-exchange");
      expect(init.method).toBe("POST");
      expect(JSON.parse(init.body as string)).toEqual({ api_key: "my-dev-key" });
    });

    it("uses the constructor developerKey when no key is passed to authenticate()", async () => {
      const fetch = mockFetch({
        json: () => Promise.resolve({ access_token: "fresh-token" }),
      });
      global.fetch = fetch;

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        developerKey: "constructor-key",
      });
      await client.authenticate();

      const [, init] = (fetch.mock.calls as [string, RequestInit][])[0];
      expect(JSON.parse(init.body as string)).toEqual({ api_key: "constructor-key" });
    });

    it("throws when no developer key is available", async () => {
      const client = new NexoServerClient({ apiUrl: "http://nexo.example.com" });
      await expect(client.authenticate()).rejects.toThrow("No developer key provided");
    });

    it("throws when key-exchange returns a non-ok response", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
      });

      const client = new NexoServerClient({ apiUrl: "http://nexo.example.com" });
      await expect(client.authenticate("bad-key")).rejects.toThrow("Key exchange failed: 401");
    });
  });

  // ---- auto-authenticate ----

  describe("auto-authenticate on first request", () => {
    it("auto-authenticates when no token is set", async () => {
      let callCount = 0;
      global.fetch = vi.fn().mockImplementation((url: string) => {
        callCount++;
        if ((url as string).includes("key-exchange")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ access_token: "auto-token" }),
          });
        }
        // listMicroApps
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([]),
        });
      });

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        developerKey: "my-key",
      });

      await client.listMicroApps();
      expect(callCount).toBe(2); // key-exchange + actual request
    });

    it("does not re-authenticate on subsequent requests", async () => {
      let keyExchangeCalls = 0;
      global.fetch = vi.fn().mockImplementation((url: string) => {
        if ((url as string).includes("key-exchange")) {
          keyExchangeCalls++;
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ access_token: "cached-token" }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([]),
        });
      });

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        developerKey: "my-key",
      });

      await client.listMicroApps();
      await client.listMicroApps();

      expect(keyExchangeCalls).toBe(1);
    });
  });

  // ---- Authorization header ----

  describe("Authorization header", () => {
    it("sends Bearer token on authenticated requests", async () => {
      const fetch = mockFetch({ json: () => Promise.resolve([]) });
      global.fetch = fetch;

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        bearerToken: "my-token",
      });

      await client.listMicroApps();

      const [, init] = (fetch.mock.calls as [string, RequestInit][])[0];
      expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer my-token");
    });
  });

  // ---- NexoRequestError ----

  describe("NexoRequestError", () => {
    it("includes status code", () => {
      const err = new NexoRequestError("not found", 404);
      expect(err.status).toBe(404);
      expect(err.message).toBe("not found");
      expect(err.name).toBe("NexoRequestError");
    });

    it("is thrown when a request returns a non-ok status", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        statusText: "Forbidden",
        text: () => Promise.resolve("Access denied"),
      });

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        bearerToken: "token",
      });

      const error = await client.listMicroApps().catch((e) => e);
      expect(error).toBeInstanceOf(NexoRequestError);
      expect(error.status).toBe(403);
    });
  });

  // ---- 204 responses ----

  describe("204 No Content", () => {
    it("returns undefined for 204 responses", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        text: () => Promise.resolve(""),
        json: () => Promise.reject(new Error("No body")),
      });

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        bearerToken: "token",
      });

      const result = await client.deleteTableRecord("tbl-1", "rec-1");
      expect(result).toBeUndefined();
    });
  });

  // ---- Knowledge Packs ----

  describe("Knowledge Packs", () => {
    it("listKnowledgePacks calls correct endpoint", async () => {
      const fetch = mockFetch({ json: () => Promise.resolve([]) });
      global.fetch = fetch;

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        bearerToken: "token",
      });

      await client.listKnowledgePacks("app-123");
      const [url] = (fetch.mock.calls as [string, RequestInit][])[0];
      expect(url).toContain("/api/knowledge-packs");
      expect(url).toContain("owner_id=app-123");
    });

    it("bulkUpsertRecords sends records array in body", async () => {
      const fetch = mockFetch({ json: () => Promise.resolve({ created: 1, updated: 0, total: 1 }) });
      global.fetch = fetch;

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        bearerToken: "token",
      });

      const records = [{ record_key: "k1", data_json: { val: 1 } }];
      await client.bulkUpsertRecords("pack-1", "ds-1", records);

      const [, init] = (fetch.mock.calls as [string, RequestInit][])[0];
      expect(JSON.parse(init.body as string)).toEqual(records);
    });
  });

  // ---- getMyProfile with bearer override ----

  describe("getMyProfile", () => {
    it("uses the provided accessToken rather than the client token", async () => {
      const fetch = mockFetch({
        json: () => Promise.resolve({ id: "p-1", user_id: "u-1" }),
      });
      global.fetch = fetch;

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        bearerToken: "client-token",
      });

      await client.getMyProfile("user-specific-token");

      const [, init] = (fetch.mock.calls as [string, RequestInit][])[0];
      expect((init.headers as Record<string, string>)["Authorization"]).toBe(
        "Bearer user-specific-token",
      );
    });

    it("falls back to client token when no accessToken given", async () => {
      const fetch = mockFetch({
        json: () => Promise.resolve({ id: "p-1", user_id: "u-1" }),
      });
      global.fetch = fetch;

      const client = new NexoServerClient({
        apiUrl: "http://nexo.example.com",
        bearerToken: "client-token",
      });

      await client.getMyProfile();

      const [, init] = (fetch.mock.calls as [string, RequestInit][])[0];
      expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer client-token");
    });
  });
});
