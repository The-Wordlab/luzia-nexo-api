import { createHmac, timingSafeEqual } from "crypto";

export function signRequest(
  secret: string,
  rawBody: string,
  timestamp?: number,
): { timestamp: number; signature: string } {
  const ts = timestamp ?? Math.floor(Date.now() / 1000);
  const signedPayload = `${ts}.${rawBody}`;
  const digest = createHmac("sha256", secret)
    .update(signedPayload)
    .digest("hex");
  return { timestamp: ts, signature: `sha256=${digest}` };
}

export function verifySignature(
  secret: string,
  rawBody: string,
  timestamp: number,
  signature: string,
): boolean {
  const { signature: expected } = signRequest(secret, rawBody, timestamp);
  if (expected.length !== signature.length) return false;
  return timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}
