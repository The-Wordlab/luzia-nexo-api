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
        { event: "stream_start", data: JSON.stringify({ thread_id: "thread-1" }) },
        { event: "content_delta", data: JSON.stringify({ delta: "Mexico are" }) },
        { event: "content_delta", data: JSON.stringify({ delta: "still favourites." }) },
        {
          event: "done",
          data: JSON.stringify({
            text: "Mexico are still favourites.",
          }),
        },
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
});
