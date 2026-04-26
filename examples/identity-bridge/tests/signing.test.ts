import { describe, test, expect } from "vitest";
import { signRequest, verifySignature } from "../src/lib/signing";

describe("HMAC signing", () => {
  const secret = "test-secret-123";
  const body =
    '{"phone_e164":"+34612345678","external_user_id":"uid-1"}';
  const timestamp = 1714150000;

  test("produces deterministic signature", () => {
    const r1 = signRequest(secret, body, timestamp);
    const r2 = signRequest(secret, body, timestamp);
    expect(r1.signature).toBe(r2.signature);
    expect(r1.timestamp).toBe(timestamp);
  });

  test("signature starts with sha256=", () => {
    const { signature } = signRequest(secret, body, timestamp);
    expect(signature).toMatch(/^sha256=[a-f0-9]{64}$/);
  });

  test("different body produces different signature", () => {
    const s1 = signRequest(secret, body, timestamp);
    const s2 = signRequest(secret, '{"different": true}', timestamp);
    expect(s1.signature).not.toBe(s2.signature);
  });

  test("different timestamp produces different signature", () => {
    const s1 = signRequest(secret, body, 1000);
    const s2 = signRequest(secret, body, 2000);
    expect(s1.signature).not.toBe(s2.signature);
  });

  test("verifySignature accepts valid signature", () => {
    const { timestamp: ts, signature } = signRequest(secret, body, timestamp);
    expect(verifySignature(secret, body, ts, signature)).toBe(true);
  });

  test("verifySignature rejects wrong signature", () => {
    expect(
      verifySignature(secret, body, timestamp, "sha256=wrong"),
    ).toBe(false);
  });

  test("verifySignature rejects tampered body", () => {
    const { timestamp: ts, signature } = signRequest(secret, body, timestamp);
    expect(
      verifySignature(secret, '{"tampered": true}', ts, signature),
    ).toBe(false);
  });

  test("uses current time when no timestamp provided", () => {
    const before = Math.floor(Date.now() / 1000);
    const { timestamp: ts } = signRequest(secret, body);
    const after = Math.floor(Date.now() / 1000);
    expect(ts).toBeGreaterThanOrEqual(before);
    expect(ts).toBeLessThanOrEqual(after);
  });

  test("empty body produces valid signature", () => {
    const { signature } = signRequest(secret, "", timestamp);
    expect(signature).toMatch(/^sha256=[a-f0-9]{64}$/);
    expect(verifySignature(secret, "", timestamp, signature)).toBe(true);
  });

  // Cross-language test vector: MUST match Python webhook_signing.py output.
  // Verified: sign_webhook_request("nexo-test-secret", '{"test":true}', timestamp=1700000000)
  // produces sha256=eec459cc9b2569fc0acc7dc023b69bcc36669cbb6fab38f59ed1bacd7bd46f2e
  test("matches Python webhook_signing.py output for shared test vector", () => {
    const { signature } = signRequest(
      "nexo-test-secret",
      '{"test":true}',
      1700000000,
    );
    expect(signature).toBe(
      "sha256=eec459cc9b2569fc0acc7dc023b69bcc36669cbb6fab38f59ed1bacd7bd46f2e",
    );
  });
});
