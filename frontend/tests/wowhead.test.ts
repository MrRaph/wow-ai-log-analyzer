import { describe, expect, it } from "vitest";

import { itemUrl, spellUrl, wowheadDataLocale } from "@/lib/wowhead";

describe("wowhead url builders", () => {
  it("uses www subdomain for English spells", () => {
    expect(spellUrl(12345, "en")).toBe("https://www.wowhead.com/spell=12345");
  });

  it("uses de subdomain for German spells", () => {
    expect(spellUrl(12345, "de")).toBe("https://de.wowhead.com/spell=12345");
  });

  it("uses tbc prefix for TBC game version", () => {
    expect(spellUrl(12345, "en", "tbc")).toBe("https://www.wowhead.com/tbc/spell=12345");
  });

  it("uses wotlk prefix for WotLK game version", () => {
    expect(spellUrl(12345, "en", "wotlk")).toBe("https://www.wowhead.com/wotlk/spell=12345");
  });

  it("uses classic prefix for Classic Era game version", () => {
    expect(spellUrl(12345, "en", "classic")).toBe("https://www.wowhead.com/classic/spell=12345");
  });

  it("uses cata prefix for Cataclysm game version", () => {
    expect(spellUrl(12345, "fr", "cata")).toBe("https://fr.wowhead.com/cata/spell=12345");
  });

  it("no prefix for retail (default)", () => {
    expect(spellUrl(12345, "en", "retail")).toBe("https://www.wowhead.com/spell=12345");
  });

  it("appends ilvl/bonus/gem/ench query params for items", () => {
    const url = itemUrl(99999, "en", { ilvl: 525, bonus: [10, 20], gem: [4, 5], ench: 7 });
    expect(url).toContain("ilvl=525");
    expect(url).toContain("bonus=10:20");
    expect(url).toContain("gems=4:5");
    expect(url).toContain("ench=7");
  });

  it("appends tbc prefix to item URLs", () => {
    const url = itemUrl(9999, "en", undefined, "tbc");
    expect(url).toBe("https://www.wowhead.com/tbc/item=9999");
  });

  it("returns the wowhead-power data-locale code", () => {
    expect(wowheadDataLocale("en")).toBe("en-us");
    expect(wowheadDataLocale("de")).toBe("de");
  });
});
