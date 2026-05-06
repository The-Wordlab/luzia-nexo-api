import { describe, it, expect } from "vitest";
import { createI18n, resolveLocale, isSupported, SUPPORTED_LOCALES } from "./i18n";

describe("resolveLocale", () => {
  it("returns bootstrap locale when valid", () => {
    expect(resolveLocale("es")).toBe("es");
  });

  it("falls back to en for invalid locale", () => {
    expect(resolveLocale("zh")).toBe("en");
  });

  it("falls back to en for null", () => {
    expect(resolveLocale(null)).toBe("en");
  });
});

describe("isSupported", () => {
  it("returns true for supported locales", () => {
    for (const locale of SUPPORTED_LOCALES) {
      expect(isSupported(locale)).toBe(true);
    }
  });

  it("returns false for unsupported locales", () => {
    expect(isSupported("zh")).toBe(false);
    expect(isSupported("")).toBe(false);
  });
});

describe("createI18n", () => {
  const messages = {
    en: { HELLO: "Hello", GOODBYE: "Goodbye" },
    es: { HELLO: "Hola", GOODBYE: "Adios" },
    pt: { HELLO: "Ola" },
    fr: { HELLO: "Bonjour" },
    it: { HELLO: "Ciao" },
  };

  it("translates using current locale", () => {
    const { t, setLocale } = createI18n(messages);
    expect(t("HELLO")).toBe("Hello");
    setLocale("es");
    expect(t("HELLO")).toBe("Hola");
  });

  it("falls back to English for missing keys", () => {
    const { t, setLocale } = createI18n(messages);
    setLocale("pt");
    expect(t("GOODBYE")).toBe("Goodbye");
  });

  it("returns key for completely unknown keys", () => {
    const { t } = createI18n(messages);
    expect(t("UNKNOWN_KEY")).toBe("UNKNOWN_KEY");
  });

  it("getLocale returns the current locale", () => {
    const { getLocale, setLocale } = createI18n(messages);
    expect(getLocale()).toBe("en");
    setLocale("fr");
    expect(getLocale()).toBe("fr");
  });
});
