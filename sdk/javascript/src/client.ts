/**
 * Proactive messaging client for the Nexo Partner API.
 */

import type {
  NexoClientOptions,
  NexoErrorDetail,
  MessageResponse,
  Thread,
  Subscriber,
} from "./types.js";

/** Error thrown by NexoClient when an API request fails. */
export class NexoApiError extends Error {
  public readonly status: number;
  public readonly statusText: string;
  public readonly body: unknown;

  constructor(message: string, detail: NexoErrorDetail) {
    super(message);
    this.name = "NexoApiError";
    this.status = detail.status;
    this.statusText = detail.statusText;
    this.body = detail.body;
  }
}

/**
 * Client for the Nexo Partner API.
 *
 * Uses native fetch - no external HTTP dependencies required.
 *
 * @example
 * ```ts
 * const client = new NexoClient({
 *   apiKey: "your-app-secret",
 *   baseUrl: "https://your-nexo-instance.com",
 * });
 *
 * const message = await client.sendMessage(appId, threadId, "Hello!");
 * ```
 */
export class NexoClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;

  constructor(options: NexoClientOptions) {
    if (!options.apiKey) {
      throw new Error("apiKey is required");
    }
    if (!options.baseUrl) {
      throw new Error("baseUrl is required");
    }
    this.apiKey = options.apiKey;
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      "X-App-Secret": this.apiKey,
      "Content-Type": "application/json",
    };

    const response = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      let responseBody: unknown;
      try {
        responseBody = await response.json();
      } catch {
        responseBody = await response.text();
      }

      throw new NexoApiError(
        `API request failed: ${response.status} ${response.statusText}`,
        {
          status: response.status,
          statusText: response.statusText,
          body: responseBody,
        },
      );
    }

    return (await response.json()) as T;
  }

  /**
   * Send a proactive message to a thread.
   *
   * @param appId - The application ID.
   * @param threadId - The thread ID to send the message to.
   * @param content - The text content of the message.
   * @returns The created message.
   */
  async sendMessage(
    appId: string,
    threadId: string,
    content: string,
  ): Promise<MessageResponse> {
    return this.request<MessageResponse>(
      "POST",
      `/apps/${appId}/threads/${threadId}/messages`,
      { role: "assistant", content },
    );
  }

  /**
   * Get a thread by ID.
   *
   * @param appId - The application ID.
   * @param threadId - The thread ID.
   * @returns The thread details.
   */
  async getThread(appId: string, threadId: string): Promise<Thread> {
    return this.request<Thread>(
      "GET",
      `/apps/${appId}/threads/${threadId}`,
    );
  }

  /**
   * List subscribers for an app.
   *
   * @param appId - The application ID.
   * @returns Array of subscribers.
   */
  async listSubscribers(appId: string): Promise<Subscriber[]> {
    const data = await this.request<{ subscribers: Subscriber[] }>(
      "GET",
      `/apps/${appId}/subscribers`,
    );
    return data.subscribers;
  }

  /**
   * List threads for a subscriber.
   *
   * @param appId - The application ID.
   * @param subscriberId - The subscriber ID.
   * @returns Array of threads.
   */
  async listSubscriberThreads(
    appId: string,
    subscriberId: string,
  ): Promise<Thread[]> {
    const data = await this.request<{ threads: Thread[] }>(
      "GET",
      `/apps/${appId}/subscribers/${subscriberId}/threads`,
    );
    return data.threads;
  }
}
