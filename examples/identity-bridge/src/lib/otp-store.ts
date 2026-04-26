import { OTP_CODE } from "../config";

interface OtpEntry {
  phone: string;
  code: string;
  expiresAt: number;
  attempts: number;
}

const store = new Map<string, OtpEntry>();
const MAX_ATTEMPTS = 3;
const TTL_MS = 5 * 60 * 1000; // 5 minutes

export function createOtp(phone: string): string {
  const code = OTP_CODE; // Fixed code for demo
  store.set(phone, {
    phone,
    code,
    expiresAt: Date.now() + TTL_MS,
    attempts: 0,
  });
  return code;
}

export function verifyOtp(phone: string, code: string): boolean {
  const entry = store.get(phone);
  if (!entry) return false;
  if (Date.now() > entry.expiresAt) {
    store.delete(phone);
    return false;
  }
  entry.attempts++;
  if (entry.attempts > MAX_ATTEMPTS) {
    store.delete(phone);
    return false;
  }
  if (entry.code !== code) return false;
  store.delete(phone); // One-time use
  return true;
}
