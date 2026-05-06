/**
 * Webhook signature verification.
 *
 * HMAC-SHA256 with timing-safe comparison and timestamp skew protection.
 * Used by agent apps to verify that webhook calls come from Nexo.
 */

import crypto from "crypto";

export interface VerifySignatureOptions {
  /** Maximum allowed clock skew in seconds (default: 300). */
  maxSkewSeconds?: number;
  /** Override current time for testing. */
  nowSeconds?: number;
}

function parseTimestampSeconds(timestamp: string): number | null {
  if (!/^\d+$/u.test(timestamp)) return null;
  const parsed = Number(timestamp);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Verify a Nexo webhook signature.
 *
 * The signature format is `sha256=<hex>` computed over `<timestamp>.<rawBody>`.
 */
/**
 * Build signed request headers for the 4-header auth pattern.
 *
 * Returns an object with X-App-Id, X-App-Secret, X-Timestamp, X-Signature
 * suitable for spreading into a fetch headers object.
 */
export function signRequest(
  appId: string,
  appSecret: string,
  body: string,
  options: { signingKey?: string; nowSeconds?: number } = {},
): Record<string, string> {
  const signingKey = options.signingKey ?? appSecret;
  const ts = String(options.nowSeconds ?? Math.floor(Date.now() / 1000));
  const signedPayload = `${ts}.${body}`;
  const signature =
    "sha256=" +
    crypto.createHmac("sha256", signingKey).update(signedPayload).digest("hex");

  return {
    "X-App-Id": appId,
    "X-App-Secret": appSecret,
    "X-Timestamp": ts,
    "X-Signature": signature,
  };
}

/**
 * Verify a Nexo webhook signature.
 *
 * The signature format is `sha256=<hex>` computed over `<timestamp>.<rawBody>`.
 */
export function verifyWebhookSignature(
  secret: string,
  rawBody: string,
  timestamp: string,
  signature: string,
  options: VerifySignatureOptions = {},
): boolean {
  if (!secret || !timestamp || !signature) return false;
  const timestampSeconds = parseTimestampSeconds(timestamp);
  if (timestampSeconds === null) return false;

  const maxSkewSeconds = options.maxSkewSeconds ?? 300;
  const nowSeconds = options.nowSeconds ?? Math.floor(Date.now() / 1000);
  if (Math.abs(nowSeconds - timestampSeconds) > maxSkewSeconds) return false;

  const signedPayload = `${timestamp}.${rawBody}`;
  const expected =
    "sha256=" +
    crypto.createHmac("sha256", secret).update(signedPayload).digest("hex");

  const actualBuffer = Buffer.from(signature, "utf8");
  const expectedBuffer = Buffer.from(expected, "utf8");
  if (actualBuffer.length !== expectedBuffer.length) return false;

  return crypto.timingSafeEqual(actualBuffer, expectedBuffer);
}
