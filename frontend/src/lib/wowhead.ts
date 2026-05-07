import type { Locale } from "@/i18n/config";

const HOST: Record<Locale, string> = { en: "www", de: "de" };

export function spellUrl(spellId: number, locale: Locale): string {
  return `https://${HOST[locale]}.wowhead.com/spell=${spellId}`;
}

export function itemUrl(itemId: number, locale: Locale, extras?: { ilvl?: number | null; bonus?: number[]; gem?: number[]; ench?: number | null }): string {
  const parts: string[] = [];
  if (extras?.ilvl) parts.push(`ilvl=${extras.ilvl}`);
  if (extras?.bonus?.length) parts.push(`bonus=${extras.bonus.join(":")}`);
  if (extras?.gem?.length) parts.push(`gems=${extras.gem.join(":")}`);
  if (extras?.ench) parts.push(`ench=${extras.ench}`);
  const qs = parts.length ? `?${parts.join("&")}` : "";
  return `https://${HOST[locale]}.wowhead.com/item=${itemId}${qs}`;
}

/** Locale that the wowhead_power.js script should pick up. */
export function wowheadDataLocale(locale: Locale): string {
  return locale === "de" ? "de" : "en-us";
}
