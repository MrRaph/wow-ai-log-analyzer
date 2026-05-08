// Wowhead / Warcraft Logs parse-percentile colour scale.
//
//   100        → Artifact (gold)
//   99-99.99   → Astounding (orange)
//   95-98      → Legendary (pink)
//   75-94      → Epic (purple)
//   50-74      → Rare (blue)
//   25-49      → Uncommon (green)
//   <25        → Common (grey)
//
// ``foreground`` is the saturated colour for text; ``background`` is a
// translucent variant designed to sit on top of ``bg-bg-3`` style chips.

export type ParsePercentColors = {
  foreground: string;
  background: string;
};

export function parseColorFor(percent: number | null | undefined): ParsePercentColors {
  if (percent === null || percent === undefined) {
    return { foreground: "#71717a", background: "rgba(120,120,120,0.20)" }; // zinc-500
  }
  if (percent >= 100) return { foreground: "#e5cc80", background: "rgba(229,204,128,0.18)" };
  if (percent >= 99) return { foreground: "#ff8000", background: "rgba(255,128,0,0.18)" };
  if (percent >= 95) return { foreground: "#e268a8", background: "rgba(226,104,168,0.18)" };
  if (percent >= 75) return { foreground: "#a335ee", background: "rgba(163,53,238,0.18)" };
  if (percent >= 50) return { foreground: "#0070dd", background: "rgba(0,112,221,0.18)" };
  if (percent >= 25) return { foreground: "#1eff00", background: "rgba(30,255,0,0.18)" };
  return { foreground: "#9ca3af", background: "rgba(120,120,120,0.18)" }; // grey
}

export function formatParsePercent(percent: number | null | undefined): string {
  if (percent === null || percent === undefined) return "—";
  return Math.round(percent).toString();
}
