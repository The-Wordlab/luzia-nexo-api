/**
 * Webhook signature verification utilities.
 *
 * Signing algorithm (matches backend/app/services/webhook_signing.py):
 *   1. Build signed_payload = "{timestamp}.{raw_body}"
 *   2. Compute HMAC-SHA256(secret, signed_payload)
 *   3. Compare with "sha256={hex_digest}"
 */

import { createHmac, timingSafeEqual } from "node:crypto";
import type { WebhookPayload } from "./types.js";

/**
 * Verify a webhook signature from Nexo.
 *
 * @param payload - The raw request body string (exact bytes sent over HTTP).
 * @param signature - The value of the X-Signature header.
 * @param timestamp - The value of the X-Timestamp header.
 * @param secret - Your webhook secret (from app configuration).
 * @returns true if the signature is valid, false otherwise.
 */
export function verifyWebhookSignature(
  payload: string,
  signature: string,
  timestamp: string,
  secret: string,
): boolean {
  if (!payload || !signature || !timestamp || !secret) {
    return false;
  }

  try {
    const signedPayload = `${timestamp}.${payload}`;
    const expected =
      "sha256=" +
      createHmac("sha256", secret).update(signedPayload).digest("hex");

    const a = Buffer.from(signature, "utf8");
    const b = Buffer.from(expected, "utf8");

    if (a.length !== b.length) {
      return false;
    }

    return timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

/**
 * Parse and validate a webhook payload from the raw request body.
 *
 * @param body - The raw JSON string from the request body.
 * @returns The parsed webhook payload.
 * @throws Error if the body is not valid JSON or is missing required fields.
 */
export function parseWebhookPayload(body: string): WebhookPayload {
  let data: unknown;
  try {
    data = JSON.parse(body);
  } catch {
    throw new Error("Invalid JSON in webhook body");
  }

  if (typeof data !== "object" || data === null) {
    throw new Error("Webhook payload must be a JSON object");
  }

  const obj = data as Record<string, unknown>;

  // Validate required fields
  if (!obj.app || typeof obj.app !== "object") {
    throw new Error("Webhook payload missing required field: app");
  }
  if (!obj.thread || typeof obj.thread !== "object") {
    throw new Error("Webhook payload missing required field: thread");
  }
  if (!obj.message || typeof obj.message !== "object") {
    throw new Error("Webhook payload missing required field: message");
  }
  if (!obj.event || typeof obj.event !== "string") {
    throw new Error("Webhook payload missing required field: event");
  }

  return data as WebhookPayload;
}
