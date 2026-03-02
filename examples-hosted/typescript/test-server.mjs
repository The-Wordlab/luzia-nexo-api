import assert from "node:assert/strict";
import test from "node:test";

import { isAuthorized, processRequest } from "./server.mjs";

const secret = "test-secret";

test("health endpoint is public", () => {
  const result = processRequest("GET", "/health", {}, "", secret);
  assert.equal(result.status, 200);
  assert.equal(result.body.status, "ok");
});

test("info endpoints are public", () => {
  const rootResult = processRequest("GET", "/", {}, "", secret);
  const infoResult = processRequest("GET", "/info?format=json", {}, "", secret);
  assert.equal(rootResult.status, 200);
  assert.equal(infoResult.status, 200);
  assert.equal(typeof rootResult.body, "string");
  assert.equal(rootResult.contentType, "text/html; charset=utf-8");
  assert.equal(infoResult.contentType, "application/json");
  assert.equal(infoResult.body.repository_url, "https://github.com/The-Wordlab/luzia-nexo-api");
  assert.equal(infoResult.body.partner_portal_url, "https://nexo.luzia.com/partners");
  assert.equal(infoResult.body.api_secret_help.contact_email, "mmm@luzia.com");
  assert.equal(
    infoResult.body.endpoints.some((e) => e.path === "/webhook/minimal"),
    true,
  );
});

test("auth with X-App-Secret works", () => {
  const ok = isAuthorized({ "x-app-secret": secret }, secret);
  assert.equal(ok, true);
});

test("webhook rejects unauthorized request", () => {
  const result = processRequest("POST", "/webhook/minimal", {}, "{}", secret);
  assert.equal(result.status, 401);
});

test("webhook accepts authorized request", () => {
  const result = processRequest(
    "POST",
    "/webhook/minimal",
    { "x-app-secret": secret },
    '{"message":{"content":"hello"}}',
    secret,
  );
  assert.equal(result.status, 200);
  assert.deepEqual(result.body, { reply: "Echo: hello" });
});
