"use client";
import type { Locale } from "@/i18n/config";
import { itemUrl } from "@/lib/wowhead";

interface Props {
  itemId: number;
  locale: Locale;
  fallback?: string;
  ilvl?: number | null;
  bonus?: number[];
  gem?: number[];
  ench?: number | null;
}

export function ItemLink({ itemId, locale, fallback, ilvl, bonus, gem, ench }: Props) {
  return (
    <a
      href={itemUrl(itemId, locale, { ilvl, bonus, gem, ench })}
      target="_blank"
      rel="noopener noreferrer"
      data-wh-icon-size="small"
      className="inline-flex items-center gap-1 align-middle text-accent hover:underline"
    >
      {fallback ?? `Item ${itemId}`}
    </a>
  );
}
