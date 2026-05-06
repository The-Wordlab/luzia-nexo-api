import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  buildAgentDeviceThreadStorageKey,
  buildAgentThreadStorageKey,
  clearAgentThreadStorage,
  clearAgentThreadStorageForApp,
  extractPromptSuggestionsFromAgentCard,
  loadAgentPromptSuggestions,
  migrateAgentThreadStorage,
} from "./agent-utils";

class MemoryStorage implements Storage {
  private readonly map = new Map<string, string>();

  get length(): number {
    return this.map.size;
  }

  clear(): void {
    this.map.clear();
  }

  getItem(key: string): string | null {
    return this.map.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.map.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.map.delete(key);
  }

  setItem(key: string, value: string): void {
    this.map.set(key, value);
  }
}

const localStorageStub = new MemoryStorage();

describe("agent-utils", () => {
  const originalLocalStorage = globalThis.localStorage;

  beforeEach(() => {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: localStorageStub,
    });
    localStorageStub.clear();
  });

  afterEach(() => {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: originalLocalStorage,
    });
  });

  it("builds stable thread storage keys", () => {
    expect(
      buildAgentThreadStorageKey("nexo_agent_thread", "app-1", "user-1"),
    ).toBe("nexo_agent_thread:app-1:user-1");
    expect(
      buildAgentDeviceThreadStorageKey(
        "nexo_agent_thread",
        "app-1",
        "device-1",
      ),
    ).toBe("nexo_agent_thread:app-1:device:device-1");
  });

  it("migrates a device-scoped thread into the user-scoped key", () => {
    localStorage.setItem(
      "nexo_agent_thread:app-1:device:device-1",
      "thread-123",
    );

    const migrated = migrateAgentThreadStorage({
      storagePrefix: "nexo_agent_thread",
      appId: "app-1",
      userId: "user-1",
      deviceKey: "device-1",
    });

    expect(migrated).toBe("thread-123");
    expect(
      localStorage.getItem("nexo_agent_thread:app-1:user-1"),
    ).toBe("thread-123");
  });

  it("clears both user and device keys when requested", () => {
    localStorage.setItem("nexo_agent_thread:app-1:user-1", "thread-123");
    localStorage.setItem(
      "nexo_agent_thread:app-1:device:device-1",
      "thread-123",
    );

    clearAgentThreadStorage({
      storagePrefix: "nexo_agent_thread",
      appId: "app-1",
      userId: "user-1",
      deviceKey: "device-1",
    });

    expect(
      localStorage.getItem("nexo_agent_thread:app-1:user-1"),
    ).toBeNull();
    expect(
      localStorage.getItem("nexo_agent_thread:app-1:device:device-1"),
    ).toBeNull();
  });

  it("clears all thread keys for one app", () => {
    localStorage.setItem("nexo_agent_thread:app-1:user-1", "thread-1");
    localStorage.setItem("nexo_agent_thread:app-1:user-2", "thread-2");
    localStorage.setItem("nexo_agent_thread:app-2:user-1", "thread-3");

    clearAgentThreadStorageForApp("nexo_agent_thread", "app-1");

    expect(
      localStorage.getItem("nexo_agent_thread:app-1:user-1"),
    ).toBeNull();
    expect(
      localStorage.getItem("nexo_agent_thread:app-1:user-2"),
    ).toBeNull();
    expect(
      localStorage.getItem("nexo_agent_thread:app-2:user-1"),
    ).toBe("thread-3");
  });

  it("extracts capability-matched prompt suggestions from an agent card", () => {
    expect(
      extractPromptSuggestionsFromAgentCard(
        {
          capabilities: {
            items: [
              {
                name: "other.capability",
                metadata: { prompt_suggestions: ["Ignore me"] },
              },
              {
                name: "wc2026.ask_expert",
                metadata: { prompt_suggestions: ["Who wins Group A?"] },
              },
            ],
          },
        },
        "wc2026.ask_expert",
      ),
    ).toEqual(["Who wins Group A?"]);
  });

  it("prefers skill example invocations from a per-app agent card", () => {
    expect(
      extractPromptSuggestionsFromAgentCard(
        {
          skills: [
            {
              id: "nutrition.ask_expert",
              luzia: {
                example_invocations: [
                  "How much protein have I had today?",
                  "Log my breakfast",
                ],
              },
            },
          ],
        },
        "nutrition.ask_expert",
      ),
    ).toEqual([
      "How much protein have I had today?",
      "Log my breakfast",
    ]);
  });

  it("loads prompt suggestions from an agent card URL", async () => {
    const suggestions = await loadAgentPromptSuggestions(
      "https://service.local/api/apps/wc2026/agent.json",
      {
        capabilityName: "wc2026.ask_expert",
        fetchImpl: async () =>
          new Response(
            JSON.stringify({
              capabilities: {
                items: [
                  {
                    name: "wc2026.ask_expert",
                    metadata: { prompt_suggestions: ["Who wins Group A?"] },
                  },
                ],
              },
            }),
            { status: 200 },
          ),
      },
    );

    expect(suggestions).toEqual(["Who wins Group A?"]);
  });
});
