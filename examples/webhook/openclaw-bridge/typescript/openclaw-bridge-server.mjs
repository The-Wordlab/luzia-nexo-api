/**
 * Nexo -> OpenClaw bridge webhook.
 *
 * Receives Nexo partner webhook payloads and forwards user input to an
 * OpenClaw Gateway `/v1/responses` endpoint.
 */
import http from "node:http";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const PORT = parseInt(process.env.PORT || "8082", 10);
const DEFAULT_SCHEMA_VERSION = "2026-03-01";

export function verifySignature(secret, rawBody, timestamp, signature) {
  if (!secret || !timestamp || !signature) return true;
  try {
    const signed = `${timestamp}.${rawBody}`;
    const expected =
      "sha256=" +
      crypto.createHmac("sha256", secret).update(signed).digest("hex");
    const a = Buffer.from(signature, "utf8");
    const b = Buffer.from(expected, "utf8");
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

function extractOpenClawText(body) {
  if (typeof body?.output_text === "string" && body.output_text.trim()) {
    return body.output_text.trim();
  }

  if (Array.isArray(body?.choices) && body.choices.length > 0) {
    const content = body.choices[0]?.message?.content;
    if (typeof content === "string" && content.trim()) {
      return content.trim();
    }
  }

  const output = body?.output;
  if (Array.isArray(output)) {
    for (const item of output) {
      const content = item?.content;
      if (!Array.isArray(content)) continue;
      for (const part of content) {
        if (typeof part?.text === "string" && part.text.trim()) {
          return part.text.trim();
        }
      }
    }
  }

  return "";
}

function extractOpenClawDelta(eventType, data) {
  if (eventType === "response.output_text.delta" && typeof data?.delta === "string") {
    return data.delta;
  }
  if (typeof data?.delta === "string") {
    return data.delta;
  }
  if (typeof data?.text === "string") {
    return data.text;
  }
  return "";
}

function buildOpenClawInput(payload) {
  const content = payload?.message?.content ?? "";
  if (typeof content !== "string" || !content.trim()) {
    return "";
  }
  return content.trim();
}

function parseJsonSafe(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function isStreamRequested(payload, headers = {}) {
  if (payload?.stream === true || payload?.metadata?.stream === true) {
    return true;
  }
  const accept = String(headers["accept"] ?? "").toLowerCase();
  return accept.includes("text/event-stream");
}

function buildRequestContext(payload) {
  const input = buildOpenClawInput(payload);
  const threadId = payload?.thread?.id ? String(payload.thread.id) : "anonymous";
  const sessionKey = `nexo:thread:${threadId}`;
  return { input, threadId, sessionKey };
}

function resolveBridgeAuth(headers = {}, opts = {}) {
  const bridgeAccessKey = opts.bridgeAccessKey ?? process.env.BRIDGE_ACCESS_KEY ?? "";
  if (!bridgeAccessKey) {
    return { ok: true };
  }
  const provided = String(headers["x-bridge-key"] ?? "").trim();
  if (!provided) {
    return { ok: false, status: 401, error: "Missing X-Bridge-Key" };
  }
  const a = Buffer.from(provided, "utf8");
  const b = Buffer.from(bridgeAccessKey, "utf8");
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    return { ok: false, status: 401, error: "Invalid X-Bridge-Key" };
  }
  return { ok: true };
}

function resolveOpenClawToken(headers = {}, opts = {}) {
  const serverToken = opts.openclawToken ?? process.env.OPENCLAW_GATEWAY_TOKEN ?? "";
  if (serverToken) {
    return serverToken;
  }
  const allowRequestToken =
    opts.allowRequestOpenClawToken ?? process.env.ALLOW_REQUEST_OPENCLAW_TOKEN === "true";
  if (!allowRequestToken) {
    return "";
  }
  return String(headers["x-openclaw-gateway-token"] ?? "").trim();
}

function resolveSessionKey(payload, headers = {}, defaultSessionKey, opts = {}) {
  const allowRequestSessionKey =
    opts.allowRequestSessionKey ?? process.env.ALLOW_REQUEST_SESSION_KEY === "true";
  if (!allowRequestSessionKey) {
    return defaultSessionKey;
  }
  const fromHeader = String(headers["x-openclaw-session-key"] ?? "").trim();
  if (fromHeader) {
    return fromHeader;
  }
  const fromPayload = String(payload?.metadata?.openclaw_session_key ?? "").trim();
  if (fromPayload) {
    return fromPayload;
  }
  return defaultSessionKey;
}

function buildOpenClawRequest({ input, openclawAgentId, stream }) {
  return {
    model: `openclaw:${openclawAgentId}`,
    input,
    stream,
  };
}

function normalizeBaseUrl(baseUrl) {
  const normalized = String(baseUrl || "http://127.0.0.1:18789").replace(/\/$/, "");
  // Accept either a gateway base URL or a full /v1/responses URL.
  return normalized.replace(/\/v1\/responses$/i, "");
}

function buildOpenClawHeaders({ openclawToken, openclawAgentId, sessionKey }) {
  const headers = {
    Authorization: `Bearer ${openclawToken}`,
    "Content-Type": "application/json",
    "x-openclaw-agent-id": openclawAgentId,
    "x-openclaw-session-key": sessionKey,
  };
  return headers;
}

async function callOpenClawResponses({
  openclawBaseUrl,
  openclawToken,
  openclawAgentId,
  sessionKey,
  input,
  stream,
  fetchImpl,
  originHeaderName,
  originHeaderValue,
}) {
  const headers = buildOpenClawHeaders({ openclawToken, openclawAgentId, sessionKey });
  if (originHeaderName && originHeaderValue) {
    headers[originHeaderName] = originHeaderValue;
  }
  return await fetchImpl(`${normalizeBaseUrl(openclawBaseUrl)}/v1/responses`, {
    method: "POST",
    headers,
    body: JSON.stringify(buildOpenClawRequest({ input, openclawAgentId, stream })),
  });
}

export async function processWebhook(raw, headers = {}, opts = {}) {
  const {
    secret = "",
    openclawBaseUrl = process.env.OPENCLAW_BASE_URL || "http://127.0.0.1:18789",
    openclawAgentId = process.env.OPENCLAW_AGENT_ID || "main",
    openclawOriginHeaderName =
      process.env.OPENCLAW_ORIGIN_HEADER_NAME || "X-Nexo-Bridge-Key",
    openclawOriginHeaderValue = process.env.OPENCLAW_ORIGIN_HEADER_VALUE || "",
    fetchImpl = globalThis.fetch,
  } = opts;

  const ts = (headers["x-timestamp"] ?? "").toString();
  const sig = (headers["x-signature"] ?? "").toString();

  if (secret && !verifySignature(secret, raw, ts, sig)) {
    return { status: 401, body: null };
  }

  const bridgeAuth = resolveBridgeAuth(headers, opts);
  if (!bridgeAuth.ok) {
    return { status: bridgeAuth.status, body: { error: bridgeAuth.error } };
  }

  const payload = parseJsonSafe(raw);
  if (!payload) {
    return { status: 400, body: { error: "Invalid JSON" } };
  }

  const { input, threadId, sessionKey: defaultSessionKey } = buildRequestContext(payload);
  if (!input) {
    return { status: 400, body: { error: "Missing message.content" } };
  }

  const openclawToken = resolveOpenClawToken(headers, opts);
  if (!openclawToken) {
    return { status: 500, body: { error: "Missing OPENCLAW_GATEWAY_TOKEN" } };
  }
  const sessionKey = resolveSessionKey(payload, headers, defaultSessionKey, opts);

  let upstream;
  try {
    upstream = await callOpenClawResponses({
      openclawBaseUrl,
      openclawToken,
      openclawAgentId,
      sessionKey,
      input,
      stream: false,
      fetchImpl,
      originHeaderName: openclawOriginHeaderName,
      originHeaderValue: openclawOriginHeaderValue,
    });
  } catch (error) {
    return {
      status: 502,
      body: {
        schema_version: DEFAULT_SCHEMA_VERSION,
        status: "error",
        content_parts: [{ type: "text", text: `OpenClaw connection failed: ${String(error)}` }],
      },
    };
  }

  if (!upstream.ok) {
    const rawError = await upstream.text();
    return {
      status: 502,
      body: {
        schema_version: DEFAULT_SCHEMA_VERSION,
        status: "error",
        content_parts: [
          {
            type: "text",
            text: `OpenClaw upstream error (${upstream.status}): ${rawError.slice(0, 500)}`,
          },
        ],
      },
    };
  }

  let upstreamBody;
  try {
    upstreamBody = await upstream.json();
  } catch {
    upstreamBody = {};
  }

  const text = extractOpenClawText(upstreamBody) || "No response from OpenClaw.";

  return {
    status: 200,
    body: {
      schema_version: DEFAULT_SCHEMA_VERSION,
      status: "completed",
      content_parts: [{ type: "text", text }],
      metadata: {
        provider: "openclaw",
        agent_id: openclawAgentId,
        thread_id: threadId,
        prompt_suggestions: [
          "Help me plan my week",
          "Draft an email to my team about project updates",
          "Give me 3 practical options to improve my productivity",
        ],
      },
    },
  };
}

function parseSseBlock(block) {
  const lines = block.split(/\r?\n/);
  let eventType = "";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return {
    eventType,
    data: dataLines.join("\n"),
  };
}

function writeNexoDelta(res, text) {
  if (typeof text !== "string" || !text) {
    return;
  }
  res.write(`data: ${JSON.stringify({ type: "delta", text })}\n\n`);
}

function writeNexoDone(res) {
  res.write(
    `data: ${JSON.stringify({
      type: "done",
      metadata: {
        prompt_suggestions: [
          "Help me plan my week",
          "Draft an email to my team about project updates",
          "Give me 3 practical options to improve my productivity",
        ],
      },
    })}\n\n`,
  );
}

export async function streamWebhook(raw, headers = {}, res, opts = {}) {
  const {
    secret = "",
    openclawBaseUrl = process.env.OPENCLAW_BASE_URL || "http://127.0.0.1:18789",
    openclawAgentId = process.env.OPENCLAW_AGENT_ID || "main",
    openclawOriginHeaderName =
      process.env.OPENCLAW_ORIGIN_HEADER_NAME || "X-Nexo-Bridge-Key",
    openclawOriginHeaderValue = process.env.OPENCLAW_ORIGIN_HEADER_VALUE || "",
    fetchImpl = globalThis.fetch,
  } = opts;

  const ts = (headers["x-timestamp"] ?? "").toString();
  const sig = (headers["x-signature"] ?? "").toString();

  if (secret && !verifySignature(secret, raw, ts, sig)) {
    return { status: 401, body: null, streamed: false };
  }

  const bridgeAuth = resolveBridgeAuth(headers, opts);
  if (!bridgeAuth.ok) {
    return { status: bridgeAuth.status, body: { error: bridgeAuth.error }, streamed: false };
  }

  const payload = parseJsonSafe(raw);
  if (!payload) {
    return { status: 400, body: { error: "Invalid JSON" }, streamed: false };
  }

  const { input, sessionKey: defaultSessionKey } = buildRequestContext(payload);
  if (!input) {
    return { status: 400, body: { error: "Missing message.content" }, streamed: false };
  }

  const openclawToken = resolveOpenClawToken(headers, opts);
  if (!openclawToken) {
    return {
      status: 500,
      body: { error: "Missing OPENCLAW_GATEWAY_TOKEN" },
      streamed: false,
    };
  }
  const sessionKey = resolveSessionKey(payload, headers, defaultSessionKey, opts);

  let upstream;
  try {
    upstream = await callOpenClawResponses({
      openclawBaseUrl,
      openclawToken,
      openclawAgentId,
      sessionKey,
      input,
      stream: true,
      fetchImpl,
      originHeaderName: openclawOriginHeaderName,
      originHeaderValue: openclawOriginHeaderValue,
    });
  } catch (error) {
    return {
      status: 502,
      body: {
        schema_version: DEFAULT_SCHEMA_VERSION,
        status: "error",
        content_parts: [{ type: "text", text: `OpenClaw connection failed: ${String(error)}` }],
      },
      streamed: false,
    };
  }

  if (!upstream.ok) {
    const rawError = await upstream.text();
    return {
      status: 502,
      body: {
        schema_version: DEFAULT_SCHEMA_VERSION,
        status: "error",
        content_parts: [
          {
            type: "text",
            text: `OpenClaw upstream error (${upstream.status}): ${rawError.slice(0, 500)}`,
          },
        ],
      },
      streamed: false,
    };
  }

  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  });

  const contentType = String(upstream.headers?.get?.("content-type") || "").toLowerCase();

  if (!contentType.includes("text/event-stream") || !upstream.body) {
    let upstreamBody;
    try {
      upstreamBody = await upstream.json();
    } catch {
      upstreamBody = {};
    }
    const text = extractOpenClawText(upstreamBody) || "No response from OpenClaw.";
    writeNexoDelta(res, text);
    writeNexoDone(res);
    res.end();
    return { status: 200, streamed: true };
  }

  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let doneSent = false;

  const flushBlock = (block) => {
    const parsed = parseSseBlock(block);
    if (!parsed) {
      return;
    }
    if (parsed.data === "[DONE]") {
      if (!doneSent) {
        writeNexoDone(res);
        doneSent = true;
      }
      return;
    }

    let dataObj = null;
    try {
      dataObj = JSON.parse(parsed.data);
    } catch {
      dataObj = null;
    }

    const delta = extractOpenClawDelta(parsed.eventType, dataObj);
    if (delta) {
      writeNexoDelta(res, delta);
      return;
    }

    if (parsed.eventType === "response.completed" && !doneSent) {
      writeNexoDone(res);
      doneSent = true;
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let splitAt = buffer.indexOf("\n\n");
    while (splitAt !== -1) {
      const block = buffer.slice(0, splitAt);
      buffer = buffer.slice(splitAt + 2);
      flushBlock(block);
      splitAt = buffer.indexOf("\n\n");
    }
  }

  if (buffer.trim()) {
    flushBlock(buffer.trim());
  }

  if (!doneSent) {
    writeNexoDone(res);
  }
  res.end();
  return { status: 200, streamed: true };
}

export function createServer(configProvider = () => ({
  secret: process.env.OPENCLAW_WEBHOOK_SECRET || process.env.WEBHOOK_SECRET || "",
  bridgeAccessKey: process.env.BRIDGE_ACCESS_KEY || "",
  openclawBaseUrl: process.env.OPENCLAW_BASE_URL || "http://127.0.0.1:18789",
  openclawToken: process.env.OPENCLAW_GATEWAY_TOKEN || "",
  openclawAgentId: process.env.OPENCLAW_AGENT_ID || "main",
  openclawOriginHeaderName:
    process.env.OPENCLAW_ORIGIN_HEADER_NAME || "X-Nexo-Bridge-Key",
  openclawOriginHeaderValue: process.env.OPENCLAW_ORIGIN_HEADER_VALUE || "",
  allowRequestSessionKey: process.env.ALLOW_REQUEST_SESSION_KEY === "true",
  allowRequestOpenClawToken: process.env.ALLOW_REQUEST_OPENCLAW_TOKEN === "true",
})) {
  return http.createServer((req, res) => {
    if (req.method === "GET" && req.url === "/") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          service: "webhook-openclaw-bridge-typescript",
          description: "Bridge from Nexo webhook payloads to OpenClaw /v1/responses.",
          routes: [
            {
              path: "/webhook",
              method: "POST",
              description: "Main webhook endpoint (JSON and SSE modes).",
              auth: "Optional OPENCLAW_WEBHOOK_SECRET (or WEBHOOK_SECRET fallback) and optional BRIDGE_ACCESS_KEY",
            },
          ],
          upstream: {
            base_url_env: "OPENCLAW_BASE_URL",
            token_env: "OPENCLAW_GATEWAY_TOKEN",
            origin_header_env: "OPENCLAW_ORIGIN_HEADER_VALUE",
          },
          schema_version: DEFAULT_SCHEMA_VERSION,
        }),
      );
      return;
    }

    if (req.method !== "POST" || req.url !== "/webhook") {
      res.writeHead(405, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Method Not Allowed" }));
      return;
    }

    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", async () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      const cfg = { ...configProvider() };
      const payload = parseJsonSafe(raw);

      if (isStreamRequested(payload, req.headers)) {
        const result = await streamWebhook(raw, req.headers, res, cfg);
        if (result.streamed) {
          return;
        }
        if (result.status === 401) {
          res.writeHead(401);
          res.end();
          return;
        }
        res.writeHead(result.status, { "Content-Type": "application/json" });
        res.end(JSON.stringify(result.body));
        return;
      }

      const result = await processWebhook(raw, req.headers, cfg);

      if (result.status === 401) {
        res.writeHead(401);
        res.end();
        return;
      }

      res.writeHead(result.status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(result.body));
    });
  });
}

function startServer() {
  const server = createServer();
  server.listen(PORT, "0.0.0.0", () => {
    console.log(`OpenClaw bridge webhook listening on http://0.0.0.0:${PORT}/webhook`);
  });
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  startServer();
}
