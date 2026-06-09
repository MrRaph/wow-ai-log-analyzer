import type { Locale } from "@/i18n/config";

const HOST: Record<Locale, string> = { en: "www", de: "de", fr: "fr" };

// Maps game_version slugs (from parser._EXPANSION_ID_TO_SLUG) to the Wowhead
// path prefix.  Retail has no prefix; Classic versions use their era prefix.
const WOWHEAD_PATH_PREFIX: Record<string, string> = {
  retail: "",
  classic: "classic/",
  tbc: "tbc/",
  wotlk: "wotlk/",
  cata: "cata/",
  mop: "mop/",
  wod: "wod/",
};

function versionPrefix(gameVersion?: string): string {
  return WOWHEAD_PATH_PREFIX[gameVersion ?? "retail"] ?? "";
}

export function spellUrl(spellId: number, locale: Locale, gameVersion?: string): string {
  return `https://${HOST[locale]}.wowhead.com/${versionPrefix(gameVersion)}spell=${spellId}`;
}

export function itemUrl(
  itemId: number,
  locale: Locale,
  extras?: { ilvl?: number | null; bonus?: number[]; gem?: number[]; ench?: number | null },
  gameVersion?: string,
): string {
  const parts: string[] = [];
  if (extras?.ilvl) parts.push(`ilvl=${extras.ilvl}`);
  if (extras?.bonus?.length) parts.push(`bonus=${extras.bonus.join(":")}`);
  if (extras?.gem?.length) parts.push(`gems=${extras.gem.join(":")}`);
  if (extras?.ench) parts.push(`ench=${extras.ench}`);
  const qs = parts.length ? `?${parts.join("&")}` : "";
  return `https://${HOST[locale]}.wowhead.com/${versionPrefix(gameVersion)}item=${itemId}${qs}`;
}

/** Locale that the wowhead_power.js script should pick up. */
export function wowheadDataLocale(locale: Locale): string {
  if (locale === "de") return "de";
  if (locale === "fr") return "fr";
  return "en-us";
}
