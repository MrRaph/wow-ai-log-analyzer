"use client";
import type { GameClass } from "@/types/api";
import type { Locale } from "@/i18n/config";

interface Props {
  cls: GameClass | undefined;
  spec?: { name_en: string; name_de: string } | null;
  locale: Locale;
}

export function ClassBadge({ cls, spec, locale }: Props) {
  if (!cls) return <span className="text-zinc-400">—</span>;
  const className = locale === "de" ? cls.name_de : cls.name_en;
  const specName = spec ? (locale === "de" ? spec.name_de : spec.name_en) : null;
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-sm font-medium"
      style={{ color: cls.color_hex }}
    >
      {specName ? `${specName} ${className}` : className}
    </span>
  );
}
