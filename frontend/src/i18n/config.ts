export const LOCALES = ["en", "de"] as const;
export type Locale = (typeof LOCALES)[number];

/** Reads ``process.env.DEFAULT_LOCALE`` AT CALL TIME so the standalone
 * server picks up the runtime value. A top-level ``const`` would be
 * evaluated when the module is first imported (during ``next build``),
 * baking whatever was set then — typically nothing. Always call this
 * function from server-side code (middleware, i18n/request) instead of
 * importing a constant.
 */
export function getDefaultLocale(): Locale {
  const raw = process.env.DEFAULT_LOCALE;
  return isLocale(raw) ? raw : "en";
}

export function isLocale(value: string | undefined | null): value is Locale {
  return !!value && (LOCALES as readonly string[]).includes(value);
}

/** Wowhead uses "www" for English and "de" for German. */
export function wowheadHost(locale: Locale): string {
  return locale === "de" ? "de" : "www";
}
