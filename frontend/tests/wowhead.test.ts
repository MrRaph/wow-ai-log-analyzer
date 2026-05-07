import { describe, expect, it } from "vitest";

import { itemUrl, spellUrl, wowheadDataLocale } from "@/lib/wowhead";

describe("wowhead url builders", () => {
  it("uses www subdomain for English spells", () => {
    expect(spellUrl(12345, "en")).toBe("https://www.wowhead.com/spell=12345");
  });

  it("uses de subdomain for German spells", () => {
    expect(spellUrl(12345, "de")).toBe("https://de.wowhead.com/spell=12345");
  });

  it("appends ilvl/bonus/gem/ench query params for items", () => {
    const url = itemUrl(99999, "en", { ilvl: 525, bonus: [10, 20], gem: [4, 5], ench: 7 });
    expect(url).toContain("ilvl=525");
    expect(url).toContain("bonus=10:20");
    expect(url).toContain("gems=4:5");
    expect(url).toContain("ench=7");
  });

  it("returns the wowhead-power data-locale code", () => {
    expect(wowheadDataLocale("en")).toBe("en-us");
    expect(wowheadDataLocale("de")).toBe("de");
  });
});
