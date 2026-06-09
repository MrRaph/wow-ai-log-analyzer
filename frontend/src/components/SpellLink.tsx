"use client";
import type { Locale } from "@/i18n/config";
import { spellUrl } from "@/lib/wowhead";

interface Props {
  spellId: number;
  locale: Locale;
  fallback?: string;
  gameVersion?: string;
}

export function SpellLink({ spellId, locale, fallback, gameVersion }: Props) {
  return (
    <a
      href={spellUrl(spellId, locale, gameVersion)}
      target="_blank"
      rel="noopener noreferrer"
      data-wh-icon-size="small"
      className="inline-flex items-center gap-1 align-middle text-accent hover:underline"
    >
      {fallback ?? `Spell ${spellId}`}
    </a>
  );
}
