"use client";

import { useEffect } from "react";
import { wowheadDataLocale } from "@/lib/wowhead";
import type { Locale } from "@/i18n/config";

declare global {
  interface Window {
    whTooltips?: { colorLinks: boolean; iconizeLinks: boolean; renameLinks: boolean };
    $WowheadPower?: { refreshLinks: () => void };
  }
}

/**
 * Loads the official Wowhead tooltip script once per session.
 * Calling refreshLinks() after navigation lets new links pick up tooltips.
 */
export function WowheadScript({ locale }: { locale: Locale }) {
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.whTooltips = { colorLinks: true, iconizeLinks: true, renameLinks: true };
    if (document.getElementById("wowhead-power-script")) {
      window.$WowheadPower?.refreshLinks();
      return;
    }
    const s = document.createElement("script");
    s.id = "wowhead-power-script";
    s.async = true;
    s.src = `https://wow.zamimg.com/widgets/power.js`;
    s.dataset.locale = wowheadDataLocale(locale);
    document.body.appendChild(s);
  }, [locale]);
  return null;
}
