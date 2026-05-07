/**
 * useAgentChat - streaming chat with a Nexo agent.
 *
 * Extracted from worldcup-server's useAskExpert hook and generalized
 * for any Nexo-hosted app. Handles:
 * - SSE streaming with progressive text rendering
 * - Thread persistence in localStorage
 * - Device-key to user-key thread migration
 * - Thread context restore on mount
 * - Suggestion extraction from responses
 * - Initial prompt suggestion bootstrap from the per-app agent card
 *
 * The hook talks to POST /a2a/messages:stream on the configured Nexo API
 * origin using A2A-native SSE events (status_update, artifact_update).
 */

import { useCallback, useEffect, useState } from "react";
import type {
  ChatMessage,
  AgentChatOptions,
  AgentChatResult,
  ContentBlock,
} from "./chat-types";
import {
  buildAgentThreadStorageKey,
  loadAgentPromptSuggestions,
  migrateAgentThreadStorage,
} from "./agent-utils";
import { buildNexoRequestInit } from "./runtime-auth";

const STREAM_RENDER_CHUNK_SIZE = 4;
const STREAM_RENDER_INTERVAL_MS = 18;
const STREAM_RENDER_SENTENCE_PAUSE_MS = 96;

let msgCounter = 0;
function makeId(): string {
  return `chat-${Date.now()}-${++msgCounter}`;
}

function parseSuggestions(contentJson: unknown): string[] {
  if (!contentJson || typeof contentJson !== "object") return [];
  const raw = (contentJson as Record<string, unknown>).prompt_suggestions;
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is string => typeof item === "string");
}

function isContentBlock(item: unknown): item is ContentBlock {
  return (
    typeof item === "object" &&
    item !== null &&
    typeof (item as Record<string, unknown>).type === "string"
  );
}

function parseContentBlocks(value: unknown): ContentBlock[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const blocks = value.filter(isContentBlock);
  return blocks.length > 0 ? blocks : undefined;
}

function extractPartnerResponseText(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const partner = value as Record<string, unknown>;
  if (typeof partner.text === "string" && partner.text.trim().length > 0) {
    return partner.text;
  }
  if (typeof partner.message === "string" && partner.message.trim().length > 0) {
    return partner.message;
  }
  const contentParts = partner.content_parts;
  if (!Array.isArray(contentParts)) return null;
  const textParts = contentParts.flatMap((part) => {
    if (!part || typeof part !== "object") return [];
    const text = (part as Record<string, unknown>).text;
    return typeof text === "string" && text.trim().length > 0 ? [text] : [];
  });
  return textParts.length > 0 ? textParts.join("\n") : null;
}

function resolveDoneText(donePayload: Record<string, unknown> | null, fallback: string): string {
  if (!donePayload) return fallback;
  if (donePayload.status === "error") {
    return fallback;
  }
  const topLevelText = donePayload.text;
  if (typeof topLevelText === "string" && topLevelText.trim().length > 0) {
    return topLevelText;
  }
  const partnerText = extractPartnerResponseText(donePayload.partner_response);
  return partnerText ?? fallback;
}

function parseSseDataLine(line: string): string | null {
  if (line.startsWith("data: ")) return line.slice(6);
  if (line.startsWith("data:")) return line.slice(5);
  return null;
}

interface ThreadContextPayload {
  messages?: Array<{
    id?: string;
    role?: string;
    content?: string;
    created_at?: string;
    content_json?: Record<string, unknown>;
  }>;
  interaction_state?: {
    lane_payload?: {
      suggestions?: unknown;
    };
  };
}

function mapThreadMessages(payload: ThreadContextPayload): ChatMessage[] {
  return (payload.messages ?? []).reduce<ChatMessage[]>((acc, msg) => {
    if (typeof msg?.role !== "string" || typeof msg?.content !== "string") return acc;
    acc.push({
      id: typeof msg.id === "string" ? msg.id : makeId(),
      role: msg.role === "assistant" ? "assistant" : "user",
      text: msg.content,
      timestamp: Date.parse(msg.created_at ?? "") || Date.now(),
    });
    return acc;
  }, []);
}

function extractSuggestionsFromContext(payload: ThreadContextPayload): string[] {
  const laneSuggestions = payload.interaction_state?.lane_payload?.suggestions;
  if (Array.isArray(laneSuggestions)) {
    return laneSuggestions.filter((item): item is string => typeof item === "string");
  }
  const reversed = [...(payload.messages ?? [])].reverse();
  const latest = reversed.find((m) => m.role === "assistant");
  if (!latest) return [];
  return parseSuggestions(latest.content_json);
}

function buildA2aPath(path: string): string {
  return `/a2a${path}`;
}

function buildThreadListStorageKey(baseKey: string): string {
  return `${baseKey}:threads`;
}

function buildActiveThreadStorageKey(baseKey: string): string {
  return `${baseKey}:active`;
}

function readStoredThreadIds(baseKey: string): string[] {
  try {
    const raw = localStorage.getItem(buildThreadListStorageKey(baseKey));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is string => typeof item === "string");
  } catch {
    return [];
  }
}

function writeStoredThreadIds(baseKey: string, threadIds: string[]): void {
  localStorage.setItem(
    buildThreadListStorageKey(baseKey),
    JSON.stringify(threadIds),
  );
}

const MUTATION_TOOLS = new Set(["create_record", "update_record", "delete_record"]);

export function useAgentChat(options: AgentChatOptions | null): AgentChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [dataVersion, setDataVersion] = useState(0);

  const storagePrefix = options?.storagePrefix ?? "nexo_agent_thread";
  const appId = options?.appId ?? null;
  const userId = options?.userId ?? null;
  const apiBaseUrl = options?.apiBaseUrl ?? null;
  const accessToken = options?.accessToken ?? null;
  const deviceKey = options?.deviceKey ?? null;
  const agentCardUrl = options?.agentCardUrl ?? null;
  const capabilityName = options?.capabilityName ?? null;
  const threadMode = options?.threadPolicy?.mode ?? "single";
  const [fallbackSuggestions, setFallbackSuggestions] = useState<string[]>([]);

  // Restore thread on mount
  useEffect(() => {
    if (!appId || !userId || !apiBaseUrl) return;
    let cancelled = false;

    (async () => {
      const key = buildAgentThreadStorageKey(storagePrefix, appId, userId);
      migrateAgentThreadStorage({
        storagePrefix,
        appId,
        userId,
        deviceKey,
      });
      let storedId = localStorage.getItem(key);
      if (threadMode === "multiple") {
        const activeKey = buildActiveThreadStorageKey(key);
        storedId =
          localStorage.getItem(activeKey) ||
          storedId ||
          readStoredThreadIds(key).at(-1) ||
          null;
      }
      if (!storedId) return;

      try {
        const resp = await fetch(
          `${apiBaseUrl}${buildA2aPath("/tasks")}?contextId=${encodeURIComponent(storedId)}&historyLength=50&pageSize=1`,
          buildNexoRequestInit({
            accessToken,
          }),
        );
        if (!resp.ok) {
          localStorage.removeItem(key);
          return;
        }
        const listPayload = await resp.json();
        const tasks = Array.isArray(listPayload.tasks) ? listPayload.tasks : [];
        const task = tasks[0];
        if (!task || typeof task !== "object") {
          localStorage.removeItem(key);
          return;
        }
        const taskRecord = task as Record<string, unknown>;
        const history = Array.isArray(taskRecord.history) ? taskRecord.history : [];
        const payload: ThreadContextPayload = {
          messages: history.map((msg: Record<string, unknown>) => {
            const firstPart = Array.isArray(msg.parts)
              ? (msg.parts[0] as Record<string, unknown> | undefined)
              : undefined;
            return {
              id: typeof msg.messageId === "string" ? msg.messageId : undefined,
              role: msg.role === "agent" ? "assistant" : "user",
              content:
                typeof firstPart?.text === "string" ? firstPart.text : "",
              content_json:
                msg.metadata &&
                typeof msg.metadata === "object" &&
                !Array.isArray(msg.metadata)
                  ? (msg.metadata as Record<string, unknown>)
                  : undefined,
            };
          }),
        };
        if (cancelled) return;

        setThreadId(
          typeof taskRecord.contextId === "string" && taskRecord.contextId.trim().length > 0
            ? taskRecord.contextId
            : storedId,
        );
        setMessages(mapThreadMessages(payload));
        const restored = extractSuggestionsFromContext(payload);
        if (restored.length > 0) setSuggestions(restored);
      } catch {
        localStorage.removeItem(key);
        if (threadMode === "multiple") {
          localStorage.removeItem(buildActiveThreadStorageKey(key));
        }
      }
    })();

    return () => { cancelled = true; };
  }, [accessToken, apiBaseUrl, appId, deviceKey, storagePrefix, threadMode, userId]);

  useEffect(() => {
    if (!agentCardUrl) return;
    let cancelled = false;

    (async () => {
      try {
        const next = await loadAgentPromptSuggestions(agentCardUrl, {
          capabilityName,
        });
        if (cancelled || next.length === 0) return;
        setFallbackSuggestions(next);
        setSuggestions((prev) => (prev.length > 0 ? prev : next));
      } catch {
        // Best effort only.
      }
    })();

    return () => { cancelled = true; };
  }, [agentCardUrl, capabilityName]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || !options) return;

      const userMsg: ChatMessage = { id: makeId(), role: "user", text: text.trim(), timestamp: Date.now() };
      setMessages((prev) => [...prev, userMsg]);
      setSending(true);
      setProgress(null);
      setError(null);
      setSuggestions([]);

      const assistantId = makeId();
      let fullText = "";
      let visibleText = "";
      let pendingDelta = "";
      let flushTimer: ReturnType<typeof setTimeout> | null = null;
      let donePayload: Record<string, unknown> | null = null;

      const updateVisible = () => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, text: visibleText } : m)),
        );
      };

      const renderChunk = () => {
        flushTimer = null;
        if (!pendingDelta) return;
        const chunk = pendingDelta.slice(0, STREAM_RENDER_CHUNK_SIZE);
        pendingDelta = pendingDelta.slice(chunk.length);
        visibleText += chunk;
        updateVisible();
        if (pendingDelta) {
          const delay = /[.!?]["')\]]?\s*$/.test(visibleText)
            ? STREAM_RENDER_SENTENCE_PAUSE_MS
            : STREAM_RENDER_INTERVAL_MS;
          flushTimer = setTimeout(renderChunk, delay);
        }
      };

      const enqueueDelta = (delta: string) => {
        pendingDelta += delta;
        if (!flushTimer) flushTimer = setTimeout(renderChunk, STREAM_RENDER_INTERVAL_MS);
      };

      const drainRender = async () => {
        while (pendingDelta || flushTimer) {
          await new Promise((r) => setTimeout(r, 10));
        }
      };

      let sawMutationTool = false;
      const storageKey = buildAgentThreadStorageKey(
        storagePrefix,
        options.appId,
        options.userId,
      );
      let assistantBubbleCreated = false;
      const ensureAssistantBubble = () => {
        if (!assistantBubbleCreated) {
          assistantBubbleCreated = true;
          setMessages((prev) => [...prev, { id: assistantId, role: "assistant", text: "", timestamp: Date.now() }]);
        }
      };

      try {
        const resp = await fetch(
          `${options.apiBaseUrl}${buildA2aPath("/messages:stream")}`,
          buildNexoRequestInit({
            accessToken: options.accessToken,
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Accept: "text/event-stream",
            },
            body: JSON.stringify({
              message: {
                messageId: makeId(),
                contextId: threadId,
                role: "user",
                parts: [{ type: "text", text: text.trim() }],
                metadata: {
                  skill_id: options.skillId ?? options.slug,
                  capability_name: options.capabilityName ?? undefined,
                  locale: options.locale ?? "en",
                },
              },
            }),
          }),
        );

        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${resp.status}`);
        }

        const reader = resp.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";
        let currentEvent = "message";
        let currentData: string[] = [];

        // Helper to extract text from A2A message parts
        const extractPartsText = (message: unknown): string | null => {
          if (!message || typeof message !== "object") return null;
          const parts = (message as Record<string, unknown>).parts;
          if (!Array.isArray(parts)) return null;
          const texts = parts
            .filter((p): p is Record<string, unknown> => typeof p === "object" && p !== null && typeof (p as Record<string, unknown>).text === "string")
            .map((p) => p.text as string);
          return texts.length > 0 ? texts.join("") : null;
        };

        const processEvent = (eventName: string, payloadText: string) => {
          if (!payloadText) return;
          let parsed: unknown = payloadText;
          try { parsed = JSON.parse(payloadText); } catch { /* raw string */ }

          if (!parsed || typeof parsed !== "object") return;
          const obj = parsed as Record<string, unknown>;

          // A2A: status_update events carry state transitions
          if (eventName === "status_update") {
            const status = obj.status as Record<string, unknown> | undefined;
            if (!status) return;
            const state = status.state as string;

            // Extract contextId from the first status_update (thread ID)
            const tid = obj.contextId;
            if (typeof tid === "string" && !threadId) {
              setThreadId(tid);
              localStorage.setItem(storageKey, tid);
              if (threadMode === "multiple") {
                localStorage.setItem(buildActiveThreadStorageKey(storageKey), tid);
                const existing = readStoredThreadIds(storageKey);
                if (!existing.includes(tid)) {
                  writeStoredThreadIds(storageKey, [...existing, tid]);
                }
              }
            }

            if (state === "working") {
              // Tool call or initial working state
              const toolName = status.tool;
              if (typeof toolName === "string" && MUTATION_TOOLS.has(toolName)) {
                sawMutationTool = true;
              }
              const progressText = extractPartsText(status.message);
              if (typeof progressText === "string" && progressText) {
                setProgress(progressText);
              }
              return;
            }

            if (state === "completed") {
              // Done - extract final text and suggestions
              const doneText = extractPartsText(status.message);
              const suggestions = status.followUpQuestions;
              donePayload = {
                text: doneText ?? fullText,
                followupQuestions: Array.isArray(suggestions) ? suggestions : [],
              };
              return;
            }

            if (state === "failed") {
              const errorText = extractPartsText(status.message) ?? "Request failed";
              if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
              pendingDelta = "";
              fullText = errorText;
              visibleText = errorText;
              updateVisible();
              setError(errorText);
              return;
            }
            return;
          }

          if (eventName === "done") {
            donePayload = obj;

            const tid = obj.contextId ?? obj.thread_id ?? obj.threadId;
            if (typeof tid === "string" && !threadId) {
              setThreadId(tid);
              localStorage.setItem(storageKey, tid);
              if (threadMode === "multiple") {
                localStorage.setItem(buildActiveThreadStorageKey(storageKey), tid);
                const existing = readStoredThreadIds(storageKey);
                if (!existing.includes(tid)) {
                  writeStoredThreadIds(storageKey, [...existing, tid]);
                }
              }
            }

            const status = obj.status;
            if (status === "error") {
              const partnerResponse = obj.partner_response;
              let formatted: string | null = null;
              if (partnerResponse && typeof partnerResponse === "object") {
                const partnerError = (partnerResponse as Record<string, unknown>).error;
                if (partnerError && typeof partnerError === "object") {
                  const errObj = partnerError as Record<string, unknown>;
                  const message = typeof errObj.message === "string" ? errObj.message : null;
                  const details = errObj.details;
                  formatted = message ?? fullText;
                  if (details && typeof details === "object") {
                    const internalMsg = (details as Record<string, unknown>).internal_message;
                    if (typeof internalMsg === "string") {
                      formatted = `${formatted}\n\nTechnical details: ${internalMsg}`;
                    }
                  }
                }
              }
              if (formatted) {
                if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
                pendingDelta = "";
                fullText = formatted;
                visibleText = formatted;
                updateVisible();
                setError(formatted);
              }
            }
            return;
          }

          // A2A: artifact_update events carry streamed text deltas
          if (eventName === "artifact_update") {
            const artifact = obj.artifact as Record<string, unknown> | undefined;
            const delta = artifact ? extractPartsText(artifact) : null;
            if (typeof delta === "string" && delta) {
              ensureAssistantBubble();
              fullText += delta;
              setProgress(null);
              enqueueDelta(delta);
            }
            return;
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (line.startsWith("event:")) {
              currentEvent = line.slice(6).trim();
            } else {
              const dataLine = parseSseDataLine(line);
              if (dataLine !== null) {
                currentData.push(dataLine);
              } else if (line === "") {
                if (currentData.length > 0) {
                  processEvent(currentEvent, currentData.join("\n"));
                  currentData = [];
                }
                currentEvent = "message";
              }
            }
          }
        }

        // Process any remaining
        if (currentData.length > 0) {
          processEvent(currentEvent, currentData.join("\n"));
        }

        await drainRender();

        // Extract suggestions from done payload
        if (donePayload) {
          let nextSuggestions: string[] = [];
          // Try content_json.prompt_suggestions (webhook path)
          const cj = donePayload["content_json"];
          if (cj && typeof cj === "object") {
            const doneSuggestions = parseSuggestions(cj);
            if (doneSuggestions.length > 0) {
              nextSuggestions = doneSuggestions;
            }
          }
          // Try top-level prompt_suggestions / follow_up_questions / followupQuestions.
          // These are raw arrays, not wrapped in content_json, so parse directly.
          // The A2A chatify mapper uses camelCase "followupQuestions".
          const rawSuggestions: unknown =
            donePayload["prompt_suggestions"] ??
            donePayload["follow_up_questions"] ??
            donePayload["followupQuestions"];
          if (Array.isArray(rawSuggestions) && rawSuggestions.length > 0) {
            const topSuggestions = rawSuggestions.filter(
              (item): item is string => typeof item === "string",
            );
            if (topSuggestions.length > 0) {
              nextSuggestions = topSuggestions;
            }
          }
          if (nextSuggestions.length > 0) {
            setSuggestions(nextSuggestions);
          } else if (fallbackSuggestions.length > 0) {
            setSuggestions(fallbackSuggestions);
          }
        }

        // Update with final full text and content blocks
        ensureAssistantBubble();
        fullText = resolveDoneText(donePayload, fullText);
        const contentBlocks = parseContentBlocks(donePayload?.["contentBlocks"]);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, text: fullText, ...(contentBlocks ? { contentBlocks } : {}) }
              : m,
          ),
        );

        // Signal data change so the app can refetch
        if (sawMutationTool) {
          setDataVersion((v) => v + 1);
        }
      } catch (err) {
        if (flushTimer) clearTimeout(flushTimer);
        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(msg);
        // Ensure the assistant bubble exists so the error is visible.
        // If the request failed before any delta, no bubble was created yet.
        ensureAssistantBubble();
        // Keep the assistant placeholder with the error text so callers
        // always see a response for every user turn.
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, text: msg } : m)),
        );
      } finally {
        setSending(false);
        setProgress(null);
      }
    },
    [fallbackSuggestions, options, threadId, storagePrefix, threadMode],
  );

  const clearThread = useCallback(() => {
    if (options) {
      const key = buildAgentThreadStorageKey(
        storagePrefix,
        options.appId,
        options.userId,
      );
      localStorage.removeItem(key);
      if (threadMode === "multiple") {
        localStorage.removeItem(buildActiveThreadStorageKey(key));
      }
    }
    setMessages([]);
    setThreadId(null);
    setSuggestions([]);
    setError(null);
  }, [options, storagePrefix, threadMode]);

  return {
    messages,
    sending,
    progress,
    error,
    suggestions,
    sendMessage,
    clearThread,
    startNewThread: clearThread,
    threadId,
    dataVersion,
  };
}
