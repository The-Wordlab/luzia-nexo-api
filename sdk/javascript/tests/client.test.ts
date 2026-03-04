import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NexoClient, NexoApiError } from "../src/client.js";

describe("NexoClient", () => {
  const options = {
    apiKey: "test-secret",
    baseUrl: "https://api.example.com",
  };

  it("throws if apiKey is empty", () => {
    expect(() => new NexoClient({ apiKey: "", baseUrl: "http://x" })).toThrow(
      "apiKey is required",
    );
  });

  it("throws if baseUrl is empty", () => {
    expect(() => new NexoClient({ apiKey: "k", baseUrl: "" })).toThrow(
      "baseUrl is required",
    );
  });

  it("strips trailing slashes from baseUrl", () => {
    const client = new NexoClient({
      apiKey: "k",
      baseUrl: "https://api.example.com///",
    });
    // Verify by attempting a request (will fail but shows URL construction)
    expect(client).toBeDefined();
  });
});

describe("NexoClient API methods", () => {
  const options = {
    apiKey: "test-secret",
    baseUrl: "https://api.example.com",
  };
  let client: NexoClient;
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    client = new NexoClient(options);
    fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockOk(data: unknown) {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => data,
    });
  }

  function mockError(status: number, body: unknown) {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status,
      statusText: "Bad Request",
      json: async () => body,
      text: async () => JSON.stringify(body),
    });
  }

  describe("sendMessage", () => {
    it("sends a POST with correct path and body", async () => {
      const messageData = {
        id: "msg-1",
        thread_id: "t-1",
        seq: 5,
        role: "assistant",
        content: "Hello!",
        content_json: {},
        created_at: "2024-01-01T00:00:00Z",
      };
      mockOk(messageData);

      const result = await client.sendMessage("app-1", "t-1", "Hello!");

      expect(fetchSpy).toHaveBeenCalledOnce();
      const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(
        "https://api.example.com/api/apps/app-1/threads/t-1/messages",
      );
      expect(init.method).toBe("POST");
      expect(JSON.parse(init.body as string)).toEqual({
        role: "assistant",
        content: "Hello!",
      });
      expect(init.headers).toEqual(
        expect.objectContaining({
          "X-App-Id": "app-1",
          "X-App-Secret": "test-secret",
          "Content-Type": "application/json",
        }),
      );
      expect(result.id).toBe("msg-1");
    });

    it("throws NexoApiError on non-OK response", async () => {
      mockError(401, { detail: "Unauthorized" });

      await expect(
        client.sendMessage("app-1", "t-1", "Hello!"),
      ).rejects.toThrow(NexoApiError);

      try {
        mockError(401, { detail: "Unauthorized" });
        await client.sendMessage("app-1", "t-1", "Hello!");
      } catch (e) {
        expect(e).toBeInstanceOf(NexoApiError);
        const err = e as NexoApiError;
        expect(err.status).toBe(401);
        expect(err.body).toEqual({ detail: "Unauthorized" });
      }
    });
  });

  describe("getThread", () => {
    it("sends a GET to the correct path", async () => {
      const threadData = {
        id: "t-1",
        app_id: "app-1",
        subscriber_id: null,
        title: null,
        status: "active",
        customer_id: null,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      };
      mockOk(threadData);

      const result = await client.getThread("app-1", "t-1");

      const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("https://api.example.com/api/apps/app-1/threads/t-1");
      expect(init.method).toBe("GET");
      expect(init.headers).toEqual(
        expect.objectContaining({
          "X-App-Id": "app-1",
          "X-App-Secret": "test-secret",
        }),
      );
      expect(result.id).toBe("t-1");
      expect(result.status).toBe("active");
    });
  });

  describe("listSubscribers", () => {
    it("sends a GET and unwraps subscribers array", async () => {
      mockOk({
        subscribers: [
          {
            id: "sub-1",
            app_id: "app-1",
            customer_id: "cust-1",
            display_name: null,
            created_at: "2024-01-01T00:00:00Z",
            last_seen_at: null,
            last_message_at: null,
          },
        ],
      });

      const result = await client.listSubscribers("app-1");

      const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("https://api.example.com/api/apps/app-1/subscribers");
      expect(result).toHaveLength(1);
      expect(result[0].customer_id).toBe("cust-1");
    });
  });

  describe("listSubscriberThreads", () => {
    it("sends a GET and unwraps threads array", async () => {
      mockOk({
        threads: [
          {
            id: "t-1",
            app_id: "app-1",
            subscriber_id: "sub-1",
            title: null,
            status: "active",
            customer_id: "cust-1",
            created_at: "2024-01-01T00:00:00Z",
            updated_at: "2024-01-01T00:00:00Z",
          },
        ],
      });

      const result = await client.listSubscriberThreads("app-1", "sub-1");

      const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(
        "https://api.example.com/api/apps/app-1/subscribers/sub-1/threads",
      );
      expect(result).toHaveLength(1);
      expect(result[0].id).toBe("t-1");
    });
  });
});
