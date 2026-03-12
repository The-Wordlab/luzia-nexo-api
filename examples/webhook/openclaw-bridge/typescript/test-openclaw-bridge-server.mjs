import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";

import { processWebhook, streamWebhook, verifySignature } from "./openclaw-bridge-server.mjs";

test("verifySignature validates HMAC sha256 payload", () => {
  const secret = "testsecret";
  const raw = '{"message":{"content":"hello"}}';
  const timestamp = "1700000000";
  const signed = `${timestamp}.${raw}`;
  const signature =
    "sha256=" + crypto.createHmac("sha256", secret).update(signed).digest("hex");

  assert.equal(verifySignature(secret, raw, timestamp, signature), true);
  assert.equal(verifySignature(secret, raw, timestamp, "sha256=bad"), false);
});

test("processWebhook calls OpenClaw responses API and returns rich success envelope", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      status: 200,
      json: async () => ({ output_text: "Hi from OpenClaw" }),
      text: async () => "",
    };
  };

  const payload = JSON.stringify({
    event: "message_received",
    thread: { id: "thread-1", customer_id: "customer-1" },
    message: { content: "hello" },
  });

  const result = await processWebhook(payload, {}, {
    openclawToken: "gateway-token",
    openclawAgentId: "main",
    openclawBaseUrl: "http://127.0.0.1:18789",
    fetchImpl,
  });

  assert.equal(result.status, 200);
  assert.deepEqual(result.body.content_parts, [{ type: "text", text: "Hi from OpenClaw" }]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://127.0.0.1:18789/v1/responses");
  assert.equal(calls[0].init.headers["x-openclaw-session-key"], "nexo:thread:thread-1");
  assert.equal(calls[0].init.headers["x-openclaw-agent-id"], "main");
  assert.equal(calls[0].init.headers["X-Nexo-Bridge-Key"], undefined);
});

test("processWebhook forwards configured OpenClaw origin header", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      status: 200,
      json: async () => ({ output_text: "ok" }),
      text: async () => "",
    };
  };

  const payload = JSON.stringify({
    thread: { id: "thread-1" },
    message: { content: "hello" },
  });

  const result = await processWebhook(payload, {}, {
    openclawToken: "gateway-token",
    openclawOriginHeaderName: "X-Nexo-Bridge-Key",
    openclawOriginHeaderValue: "origin-secret",
    fetchImpl,
  });

  assert.equal(result.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.headers["X-Nexo-Bridge-Key"], "origin-secret");
});

test("processWebhook normalizes OpenClaw base URL when /v1/responses is already included", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      status: 200,
      json: async () => ({ output_text: "ok" }),
      text: async () => "",
    };
  };

  const payload = JSON.stringify({
    thread: { id: "thread-1" },
    message: { content: "hello" },
  });

  const result = await processWebhook(payload, {}, {
    openclawToken: "gateway-token",
    openclawBaseUrl: "https://nexo-1.luzia.com/openclaw/v1/responses",
    fetchImpl,
  });

  assert.equal(result.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://nexo-1.luzia.com/openclaw/v1/responses");
});

test("processWebhook extracts text from chat-completions style fallback", async () => {
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ choices: [{ message: { content: "fallback content" } }] }),
    text: async () => "",
  });

  const result = await processWebhook('{"message":{"content":"hi"}}', {}, {
    openclawToken: "gateway-token",
    fetchImpl,
  });

  assert.equal(result.status, 200);
  assert.equal(result.body.content_parts[0].text, "fallback content");
});

test("processWebhook returns 401 when signature fails", async () => {
  let called = false;
  const fetchImpl = async () => {
    called = true;
    return { ok: true, status: 200, json: async () => ({ output_text: "unused" }) };
  };

  const result = await processWebhook(
    '{"message":{"content":"blocked"}}',
    { "x-timestamp": "1700000000", "x-signature": "sha256=bad" },
    { secret: "testsecret", openclawToken: "gateway-token", fetchImpl },
  );

  assert.equal(result.status, 401);
  assert.equal(result.body, null);
  assert.equal(called, false);
});

test("processWebhook enforces X-Bridge-Key when bridgeAccessKey is configured", async () => {
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ output_text: "unused" }),
    text: async () => "",
  });

  const payload = JSON.stringify({ message: { content: "hi" } });

  const denied = await processWebhook(payload, {}, {
    bridgeAccessKey: "demo-bridge-key",
    openclawToken: "gateway-token",
    fetchImpl,
  });
  assert.equal(denied.status, 401);
  assert.equal(denied.body.error, "Missing X-Bridge-Key");

  const allowed = await processWebhook(
    payload,
    { "x-bridge-key": "demo-bridge-key" },
    {
      bridgeAccessKey: "demo-bridge-key",
      openclawToken: "gateway-token",
      fetchImpl,
    },
  );
  assert.equal(allowed.status, 200);
});

test("processWebhook allows session-key override when enabled", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      status: 200,
      json: async () => ({ output_text: "ok" }),
      text: async () => "",
    };
  };

  const payload = JSON.stringify({
    thread: { id: "thread-default" },
    message: { content: "hi" },
  });

  await processWebhook(payload, { "x-openclaw-session-key": "demo:frontend-session" }, {
    openclawToken: "gateway-token",
    allowRequestSessionKey: true,
    fetchImpl,
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.headers["x-openclaw-session-key"], "demo:frontend-session");
});

test("processWebhook returns 502 when OpenClaw returns non-2xx", async () => {
  const fetchImpl = async () => ({
    ok: false,
    status: 503,
    text: async () => "service unavailable",
    json: async () => ({}),
  });

  const result = await processWebhook('{"message":{"content":"hi"}}', {}, {
    openclawToken: "gateway-token",
    fetchImpl,
  });

  assert.equal(result.status, 502);
  assert.equal(result.body.status, "error");
  assert.match(result.body.content_parts[0].text, /OpenClaw upstream error/);
});

function createMockSseResponse(streamText) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(streamText));
      controller.close();
    },
  });
  return {
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "text/event-stream" }),
    body,
  };
}

function createMockRes() {
  return {
    statusCode: null,
    headers: null,
    chunks: [],
    ended: false,
    writeHead(statusCode, headers) {
      this.statusCode = statusCode;
      this.headers = headers;
    },
    write(chunk) {
      this.chunks.push(String(chunk));
    },
    end(chunk) {
      if (chunk) this.chunks.push(String(chunk));
      this.ended = true;
    },
  };
}

test("streamWebhook maps OpenClaw SSE deltas to Nexo delta/done events", async () => {
  const fetchImpl = async () =>
    createMockSseResponse(
      [
        'event: response.output_text.delta\ndata: {"delta":"Hello "}\n\n',
        'event: response.output_text.delta\ndata: {"delta":"world"}\n\n',
        "data: [DONE]\n\n",
      ].join(""),
    );

  const res = createMockRes();
  const result = await streamWebhook(
    JSON.stringify({ message: { content: "hi" }, thread: { id: "t-1" } }),
    {},
    res,
    { openclawToken: "gateway-token", fetchImpl },
  );

  assert.equal(result.status, 200);
  assert.equal(result.streamed, true);
  assert.equal(res.statusCode, 200);
  assert.equal(res.headers["Content-Type"], "text/event-stream");
  const all = res.chunks.join("");
  assert.match(all, /"type":"delta","text":"Hello "/);
  assert.match(all, /"type":"delta","text":"world"/);
  assert.match(all, /"type":"done"/);
  assert.equal(res.ended, true);
});

test("streamWebhook falls back to single delta when upstream response is non-SSE", async () => {
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    body: null,
    json: async () => ({ output_text: "non-stream response" }),
  });

  const res = createMockRes();
  const result = await streamWebhook(
    JSON.stringify({ message: { content: "hi" }, thread: { id: "t-2" } }),
    {},
    res,
    { openclawToken: "gateway-token", fetchImpl },
  );

  assert.equal(result.status, 200);
  assert.equal(result.streamed, true);
  const all = res.chunks.join("");
  assert.match(all, /"type":"delta","text":"non-stream response"/);
  assert.match(all, /"type":"done"/);
});

test("streamWebhook also enforces X-Bridge-Key when configured", async () => {
  const fetchImpl = async () =>
    createMockSseResponse('event: response.output_text.delta\ndata: {"delta":"Hi"}\n\ndata: [DONE]\n\n');

  const res = createMockRes();
  const denied = await streamWebhook(
    JSON.stringify({ message: { content: "hi" } }),
    {},
    res,
    { bridgeAccessKey: "demo-bridge-key", openclawToken: "gateway-token", fetchImpl },
  );
  assert.equal(denied.status, 401);
  assert.equal(denied.streamed, false);
});

test("streamWebhook forwards configured OpenClaw origin header", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return createMockSseResponse(
      'event: response.output_text.delta\ndata: {"delta":"Hi"}\n\ndata: [DONE]\n\n',
    );
  };

  const res = createMockRes();
  const result = await streamWebhook(
    JSON.stringify({ message: { content: "hi" }, thread: { id: "t-3" } }),
    {},
    res,
    {
      openclawToken: "gateway-token",
      openclawOriginHeaderName: "X-Nexo-Bridge-Key",
      openclawOriginHeaderValue: "origin-secret",
      fetchImpl,
    },
  );

  assert.equal(result.status, 200);
  assert.equal(result.streamed, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.headers["X-Nexo-Bridge-Key"], "origin-secret");
});

test("streamWebhook normalizes OpenClaw base URL when /v1/responses is already included", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return createMockSseResponse(
      'event: response.output_text.delta\ndata: {"delta":"Hi"}\n\ndata: [DONE]\n\n',
    );
  };

  const res = createMockRes();
  const result = await streamWebhook(
    JSON.stringify({ message: { content: "hi" }, thread: { id: "t-4" } }),
    {},
    res,
    {
      openclawToken: "gateway-token",
      openclawBaseUrl: "https://nexo-1.luzia.com/openclaw/v1/responses",
      fetchImpl,
    },
  );

  assert.equal(result.status, 200);
  assert.equal(result.streamed, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://nexo-1.luzia.com/openclaw/v1/responses");
});
