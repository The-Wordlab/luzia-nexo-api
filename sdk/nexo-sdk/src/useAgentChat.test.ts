import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

import { useAgentChat } from "./useAgentChat";

function createSSEResponse(events: Array<{ event: string; data: string }>): Response {
  const lines = events.flatMap((event) => [
    `event: ${event.event}`,
    `data: ${event.data}`,
    "",
  ]);
  const text = lines.join("\n") + "\n";
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

const BASE_OPTIONS = {
  apiBaseUrl: "https://test.nexo.local",
  accessToken: "test-token",
  appId: "app-123",
  userId: "user-456",
  slug: "test-app",
  storagePrefix: "test_agent",
  locale: "en",
};

describe("useAgentChat", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    localStorage.clear();
  });

  it("uses the final done text when streamed chunks collapse word spacing", async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      createSSEResponse([
        { event: "status_update", data: JSON.stringify({ taskId: "t1", contextId: "ctx-1", status: { state: "working" } }) },
        { event: "artifact_update", data: JSON.stringify({ taskId: "t1", artifact: { artifactId: "a1", parts: [{ type: "text", text: "Mexico are" }] }, append: true }) },
        { event: "artifact_update", data: JSON.stringify({ taskId: "t1", artifact: { artifactId: "a1", parts: [{ type: "text", text: "still favourites." }] }, append: true }) },
        { event: "status_update", data: JSON.stringify({ taskId: "t1", contextId: "ctx-1", status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "Mexico are still favourites." }] } } }) },
      ]),
    );

    const { result } = renderHook(() => useAgentChat(BASE_OPTIONS));

    await act(async () => {
      await result.current.sendMessage("Who do you like?");
    });

    await waitFor(
      () => {
        const assistant = result.current.messages.at(-1);
        expect(assistant?.role).toBe("assistant");
        expect(assistant?.text).toBe("Mexico are still favourites.");
      },
      { timeout: 3000 },
    );
  });

  it("posts chat turns to the canonical A2A stream endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      createSSEResponse([
        { event: "status_update", data: JSON.stringify({ taskId: "t1", contextId: "ctx-1", status: { state: "working" } }) },
        { event: "artifact_update", data: JSON.stringify({ taskId: "t1", artifact: { artifactId: "a1", parts: [{ type: "text", text: "Hello there." }] }, append: true }) },
        { event: "status_update", data: JSON.stringify({ taskId: "t1", contextId: "ctx-1", status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "Hello there." }] } } }) },
      ]),
    );
    globalThis.fetch = fetchMock;

    const { result } = renderHook(() => useAgentChat(BASE_OPTIONS));

    await act(async () => {
      await result.current.sendMessage("Hello?");
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://test.nexo.local/a2a/messages:stream",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("uses the final done envelope to surface webhook error diagnostics", async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      createSSEResponse([
        { event: "status_update", data: JSON.stringify({ taskId: "t1", contextId: "ctx-err", status: { state: "working" } }) },
        { event: "artifact_update", data: JSON.stringify({ taskId: "t1", artifact: { artifactId: "a1", parts: [{ type: "text", text: "ERROR_TEMPORARY_FAILURE" }] }, append: true }) },
        {
          event: "done",
          data: JSON.stringify({
            contextId: "ctx-err",
            status: "error",
            partner_response: {
              error: {
                code: "ERROR_TEMPORARY_FAILURE",
                message: "I can't answer that right now. Please try again later.",
                details: {
                  internal_message: "Gemini API request failed: 429 RESOURCE_EXHAUSTED",
                },
              },
            },
            text: "ERROR_TEMPORARY_FAILURE",
          }),
        },
      ]),
    );

    const { result } = renderHook(() => useAgentChat(BASE_OPTIONS));

    await act(async () => {
      await result.current.sendMessage("Who are the favourites?");
    });

    await waitFor(
      () => {
        const assistant = result.current.messages.at(-1);
        expect(assistant?.text).toBe(
          "I can't answer that right now. Please try again later.\n\nTechnical details: Gemini API request failed: 429 RESOURCE_EXHAUSTED",
        );
      },
      { timeout: 3000 },
    );

    expect(result.current.error).toBe(
      "I can't answer that right now. Please try again later.\n\nTechnical details: Gemini API request failed: 429 RESOURCE_EXHAUSTED",
    );
  });

  it("restores existing threads from the canonical A2A task endpoint", async () => {
    localStorage.setItem(
      "test_agent:app-123:user-456",
      "thread-restore-1",
    );

    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          tasks: [
            {
              contextId: "thread-restore-1",
              history: [
                {
                  messageId: "assistant-1",
                  role: "agent",
                  parts: [{ type: "text", text: "Restored answer" }],
                },
              ],
            },
          ],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    globalThis.fetch = fetchMock;

    renderHook(() => useAgentChat(BASE_OPTIONS));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    const [url, init] = fetchMock.mock.calls[0] as [
      string,
      { headers?: Headers },
    ];
    expect(url).toBe(
      "https://test.nexo.local/a2a/tasks?contextId=thread-restore-1&historyLength=50&pageSize=1",
    );
    expect(init.headers?.get("Authorization")).toBe("Bearer test-token");
  });

  it("falls back to agent-card suggestions when a completed turn returns none", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            skills: [
              {
                id: "test-capability",
                luzia: {
                  example_invocations: ["Ask about rankings", "Show upcoming matches"],
                },
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      )
      .mockResolvedValueOnce(
        createSSEResponse([
          { event: "status_update", data: JSON.stringify({ taskId: "t1", contextId: "ctx-1", status: { state: "working" } }) },
          { event: "artifact_update", data: JSON.stringify({ taskId: "t1", artifact: { artifactId: "a1", parts: [{ type: "text", text: "Hello there." }] }, append: true }) },
          { event: "done", data: JSON.stringify({ contextId: "ctx-1", text: "Hello there." }) },
        ]),
      );

    const { result } = renderHook(() =>
      useAgentChat({
        ...BASE_OPTIONS,
        capabilityName: "test-capability",
        agentCardUrl: "https://test.nexo.local/api/apps/test-app/agent.json",
      }),
    );

    await waitFor(() => {
      expect(result.current.suggestions).toEqual([
        "Ask about rankings",
        "Show upcoming matches",
      ]);
    });

    await act(async () => {
      await result.current.sendMessage("Hi");
    });

    await waitFor(() => {
      expect(result.current.suggestions).toEqual([
        "Ask about rankings",
        "Show upcoming matches",
      ]);
    });
  });

  it("preserves prior thread ids when multi-thread mode starts a new chat", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        createSSEResponse([
          { event: "status_update", data: JSON.stringify({ taskId: "t1", contextId: "ctx-1", status: { state: "working" } }) },
          { event: "artifact_update", data: JSON.stringify({ taskId: "t1", artifact: { artifactId: "a1", parts: [{ type: "text", text: "First thread." }] }, append: true }) },
          { event: "done", data: JSON.stringify({ contextId: "ctx-1", text: "First thread." }) },
        ]),
      )
      .mockResolvedValueOnce(
        createSSEResponse([
          { event: "status_update", data: JSON.stringify({ taskId: "t2", contextId: "ctx-2", status: { state: "working" } }) },
          { event: "artifact_update", data: JSON.stringify({ taskId: "t2", artifact: { artifactId: "a2", parts: [{ type: "text", text: "Second thread." }] }, append: true }) },
          { event: "done", data: JSON.stringify({ contextId: "ctx-2", text: "Second thread." }) },
        ]),
      );

    const { result } = renderHook(() =>
      useAgentChat({
        ...BASE_OPTIONS,
        threadPolicy: { mode: "multiple", allowDeletion: false },
      }),
    );

    await act(async () => {
      await result.current.sendMessage("First");
    });

    act(() => {
      result.current.clearThread();
    });

    await act(async () => {
      await result.current.sendMessage("Second");
    });

    expect(result.current.threadId).toBe("ctx-2");
    expect(
      JSON.parse(localStorage.getItem("test_agent:app-123:user-456:threads") ?? "[]"),
    ).toEqual(["ctx-1", "ctx-2"]);
    expect(localStorage.getItem("test_agent:app-123:user-456:active")).toBe(
      "ctx-2",
    );
  });

  it("clears the active multi-thread pointer without deleting stored thread history", async () => {
    localStorage.setItem(
      "test_agent:app-123:user-456:threads",
      JSON.stringify(["ctx-1", "ctx-2"]),
    );
    localStorage.setItem("test_agent:app-123:user-456:active", "ctx-2");

    const { result } = renderHook(() =>
      useAgentChat({
        ...BASE_OPTIONS,
        threadPolicy: { mode: "multiple", allowDeletion: false },
      }),
    );

    act(() => {
      result.current.clearThread();
    });

    expect(localStorage.getItem("test_agent:app-123:user-456:active")).toBe(
      null,
    );
    expect(
      JSON.parse(localStorage.getItem("test_agent:app-123:user-456:threads") ?? "[]"),
    ).toEqual(["ctx-1", "ctx-2"]);
    expect(result.current.threadId).toBe(null);
    expect(result.current.messages).toEqual([]);
  });
});
