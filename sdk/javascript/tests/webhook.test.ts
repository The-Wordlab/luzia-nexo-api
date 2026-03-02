import { describe, it, expect } from "vitest";
import { createHmac } from "node:crypto";
import { verifyWebhookSignature, parseWebhookPayload } from "../src/webhook.js";

describe("verifyWebhookSignature", () => {
  const secret = "test-secret-key";
  const timestamp = "1700000000";
  const body = '{"event":"message_received","message":{"content":"hello"}}';

  function sign(s: string, ts: string, b: string): string {
    const signed = `${ts}.${b}`;
    return "sha256=" + createHmac("sha256", s).update(signed).digest("hex");
  }

  it("returns true for a valid signature", () => {
    const signature = sign(secret, timestamp, body);
    expect(verifyWebhookSignature(body, signature, timestamp, secret)).toBe(
      true,
    );
  });

  it("returns false for an invalid signature", () => {
    expect(
      verifyWebhookSignature(body, "sha256=invalid", timestamp, secret),
    ).toBe(false);
  });

  it("returns false when signature has wrong length", () => {
    expect(
      verifyWebhookSignature(body, "sha256=abc", timestamp, secret),
    ).toBe(false);
  });

  it("returns false for empty inputs", () => {
    expect(verifyWebhookSignature("", "sig", timestamp, secret)).toBe(false);
    expect(verifyWebhookSignature(body, "", timestamp, secret)).toBe(false);
    expect(verifyWebhookSignature(body, "sig", "", secret)).toBe(false);
    expect(verifyWebhookSignature(body, "sig", timestamp, "")).toBe(false);
  });

  it("returns false when secret does not match", () => {
    const signature = sign(secret, timestamp, body);
    expect(
      verifyWebhookSignature(body, signature, timestamp, "wrong-secret"),
    ).toBe(false);
  });

  it("returns false when body was tampered with", () => {
    const signature = sign(secret, timestamp, body);
    expect(
      verifyWebhookSignature(body + "x", signature, timestamp, secret),
    ).toBe(false);
  });

  it("returns false when timestamp does not match", () => {
    const signature = sign(secret, timestamp, body);
    expect(
      verifyWebhookSignature(body, signature, "9999999999", secret),
    ).toBe(false);
  });

  it("matches the backend signing algorithm with known test vector", () => {
    // Reproduce the exact algorithm from backend/app/services/webhook_signing.py
    const s = "my-webhook-secret";
    const ts = "1234567890";
    const b = '{"hello":"world"}';
    const signedPayload = `${ts}.${b}`;
    const expected =
      "sha256=" + createHmac("sha256", s).update(signedPayload).digest("hex");

    expect(verifyWebhookSignature(b, expected, ts, s)).toBe(true);
  });
});

describe("parseWebhookPayload", () => {
  it("parses a valid payload", () => {
    const payload = {
      event: "message_received",
      app: { id: "app-1", name: "Test App" },
      thread: { id: "thread-1", customer_id: null },
      message: {
        id: "msg-1",
        seq: 1,
        role: "user",
        content: "hello",
        content_json: {},
      },
      history_tail: [],
      timestamp: "2024-01-01T00:00:00Z",
    };
    const result = parseWebhookPayload(JSON.stringify(payload));
    expect(result.event).toBe("message_received");
    expect(result.message.content).toBe("hello");
  });

  it("parses a payload with optional tools and attachments", () => {
    const payload = {
      event: "message_received",
      app: { id: "app-1", name: "Test App" },
      thread: { id: "thread-1", customer_id: null },
      message: { id: "msg-1", seq: 1, role: "user", content: "hello", content_json: {} },
      history_tail: [],
      tools: [{ name: "websearch", enabled: true }],
      attachments: [{ media_id: "abc-123", type: "image", url: "https://example.com/img.png" }],
      metadata: { source: "test" },
      timestamp: "2024-01-01T00:00:00Z",
    };
    const result = parseWebhookPayload(JSON.stringify(payload));
    expect(result.tools).toHaveLength(1);
    expect(result.tools![0].name).toBe("websearch");
    expect(result.attachments).toHaveLength(1);
    expect(result.attachments![0].type).toBe("image");
    expect(result.metadata?.source).toBe("test");
  });

  it("parses a payload without optional fields", () => {
    const payload = {
      event: "message_received",
      app: { id: "app-1", name: "Test App" },
      thread: { id: "thread-1", customer_id: null },
      message: { id: "msg-1", seq: 1, role: "user", content: "hello", content_json: {} },
      history_tail: [],
      timestamp: "2024-01-01T00:00:00Z",
    };
    const result = parseWebhookPayload(JSON.stringify(payload));
    expect(result.tools).toBeUndefined();
    expect(result.attachments).toBeUndefined();
  });

  it("throws on invalid JSON", () => {
    expect(() => parseWebhookPayload("not json")).toThrow("Invalid JSON");
  });

  it("throws on non-object JSON", () => {
    expect(() => parseWebhookPayload('"string"')).toThrow(
      "must be a JSON object",
    );
  });

  it("throws on missing app field", () => {
    const payload = {
      event: "message_received",
      thread: { id: "t-1" },
      message: { content: "hi" },
    };
    expect(() => parseWebhookPayload(JSON.stringify(payload))).toThrow(
      "missing required field: app",
    );
  });

  it("throws on missing thread field", () => {
    const payload = {
      event: "message_received",
      app: { id: "a-1" },
      message: { content: "hi" },
    };
    expect(() => parseWebhookPayload(JSON.stringify(payload))).toThrow(
      "missing required field: thread",
    );
  });

  it("throws on missing message field", () => {
    const payload = {
      event: "message_received",
      app: { id: "a-1" },
      thread: { id: "t-1" },
    };
    expect(() => parseWebhookPayload(JSON.stringify(payload))).toThrow(
      "missing required field: message",
    );
  });

  it("throws on missing event field", () => {
    const payload = {
      app: { id: "a-1" },
      thread: { id: "t-1" },
      message: { content: "hi" },
    };
    expect(() => parseWebhookPayload(JSON.stringify(payload))).toThrow(
      "missing required field: event",
    );
  });
});
