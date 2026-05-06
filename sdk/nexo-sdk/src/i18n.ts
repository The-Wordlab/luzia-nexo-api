/**
 * Shared locale resolution for Nexo apps.
 *
 * This provides the locale infrastructure (type, resolution, get/set).
 * Each app provides its own message dictionaries.
 */

export type Locale = "en" | "es" | "pt" | "fr" | "it";

export const SUPPORTED_LOCALES: Locale[] = ["en", "es", "pt", "fr", "it"];

export function isSupported(locale: string): boolean {
  return SUPPORTED_LOCALES.includes(locale as Locale);
}

/** Resolve locale from bootstrap, query param, or default. */
export function resolveLocale(
  bootstrapLocale: string | null | undefined,
): Locale {
  if (bootstrapLocale && isSupported(bootstrapLocale)) {
    return bootstrapLocale as Locale;
  }
  if (typeof window !== "undefined") {
    const param = new URLSearchParams(window.location.search).get("locale");
    if (param && isSupported(param)) {
      return param as Locale;
    }
  }
  return "en";
}

type Messages = Record<string, string>;

/**
 * Create an i18n instance with app-specific messages.
 *
 * Usage:
 *   const { t, setLocale, getLocale } = createI18n({ en, es, pt, fr, it });
 */
export function createI18n(messages: Record<Locale, Messages>) {
  let _locale: Locale = "en";

  function setLocale(locale: string): void {
    _locale = isSupported(locale) ? (locale as Locale) : "en";
  }

  function getLocale(): Locale {
    return _locale;
  }

  function t(key: string, params?: Record<string, string>): string {
    let msg = messages[_locale]?.[key] ?? messages.en[key] ?? key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        msg = msg.replace(`{${k}}`, v);
      }
    }
    return msg;
  }

  return { t, setLocale, getLocale };
}
