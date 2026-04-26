import { describe, test, expect } from "vitest";
import { isValidE164, normalizePhone } from "../src/lib/phone";
import { createOtp, verifyOtp } from "../src/lib/otp-store";

describe("phone validation", () => {
  test("accepts valid E.164 numbers", () => {
    expect(isValidE164("+34612345678")).toBe(true);
    expect(isValidE164("+1234567890")).toBe(true);
    expect(isValidE164("+447911123456")).toBe(true);
    expect(isValidE164("+5511998765432")).toBe(true);
  });

  test("rejects numbers without leading +", () => {
    expect(isValidE164("34612345678")).toBe(false);
    expect(isValidE164("612345678")).toBe(false);
  });

  test("rejects numbers starting with +0", () => {
    expect(isValidE164("+0123456789")).toBe(false);
  });

  test("rejects too-short numbers", () => {
    expect(isValidE164("+12345")).toBe(false);
    expect(isValidE164("+1")).toBe(false);
  });

  test("rejects empty string", () => {
    expect(isValidE164("")).toBe(false);
  });

  test("rejects numbers with spaces or dashes", () => {
    expect(isValidE164("+34 612 345 678")).toBe(false);
    expect(isValidE164("+34-612-345-678")).toBe(false);
  });
});

describe("normalizePhone", () => {
  test("strips spaces", () => {
    expect(normalizePhone("+34 612 345 678")).toBe("+34612345678");
  });

  test("strips dashes", () => {
    expect(normalizePhone("+34-612-345-678")).toBe("+34612345678");
  });

  test("strips dots", () => {
    expect(normalizePhone("+34.612.345.678")).toBe("+34612345678");
  });

  test("strips parentheses", () => {
    expect(normalizePhone("+1 (555) 123-4567")).toBe("+15551234567");
  });

  test("preserves clean E.164", () => {
    expect(normalizePhone("+34612345678")).toBe("+34612345678");
  });
});

describe("OTP store", () => {
  test("createOtp and verifyOtp round-trip", () => {
    const code = createOtp("+34612345678");
    expect(verifyOtp("+34612345678", code)).toBe(true);
  });

  test("OTP is one-time use", () => {
    const code = createOtp("+34999999999");
    verifyOtp("+34999999999", code);
    expect(verifyOtp("+34999999999", code)).toBe(false);
  });

  test("wrong code rejected", () => {
    createOtp("+34111111111");
    expect(verifyOtp("+34111111111", "wrong")).toBe(false);
  });

  test("unknown phone returns false", () => {
    expect(verifyOtp("+34000000000", "123456")).toBe(false);
  });

  test("new OTP replaces old for same phone", () => {
    createOtp("+34222222222");
    const code2 = createOtp("+34222222222");
    expect(verifyOtp("+34222222222", code2)).toBe(true);
  });
});
