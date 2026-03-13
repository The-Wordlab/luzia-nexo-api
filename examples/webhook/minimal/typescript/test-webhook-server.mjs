import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";

import { processWebhook, verifySignature } from "./webhook-server.mjs";

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

test("processWebhook returns rich response for valid payload", () => {
  const result = processWebhook('{"message":{"content":"hi"}}');
  assert.equal(result.status, 200);
  assert.deepEqual(result.body, {
    schema_version: "2026-03",
    status: "completed",
    content_parts: [{ type: "text", text: "Echo: hi" }],
    metadata: {
      prompt_suggestions: [
        "Help me plan dinner",
        "Track my order status",
        "Show options under $20",
      ],
    },
  });
});

test("processWebhook uses optional profile context defensively", () => {
  const result = processWebhook(
    JSON.stringify({
      message: { content: "recommend lunch" },
      profile: {
        display_name: "Leo",
        locale: "en",
        dietary_preferences: "vegetarian",
        future_field: "ignored",
      },
    }),
  );
  assert.equal(result.status, 200);
  assert.deepEqual(result.body, {
    schema_version: "2026-03",
    status: "completed",
    content_parts: [
      {
        type: "text",
        text: "Leo, you said: recommend lunch (locale=en, dietary=vegetarian)",
      },
    ],
    metadata: {
      prompt_suggestions: [
        "Help me plan dinner",
        "Track my order status",
        "Show options under $20",
      ],
    },
  });
});

test("processWebhook returns 400 for invalid JSON", () => {
  const result = processWebhook("not-json");
  assert.equal(result.status, 400);
  assert.deepEqual(result.body, { error: "Invalid JSON" });
});

test("processWebhook returns 401 when signature fails with configured secret", () => {
  const result = processWebhook(
    '{"message":{"content":"blocked"}}',
    { "x-timestamp": "1700000000", "x-signature": "sha256=bad" },
    "testsecret",
  );
  assert.equal(result.status, 401);
  assert.equal(result.body, null);
});
