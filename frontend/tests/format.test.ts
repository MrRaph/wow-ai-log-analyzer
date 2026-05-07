import { describe, expect, it } from "vitest";

import { formatDuration, formatPercent } from "@/lib/format";

describe("format helpers", () => {
  it("formats milliseconds as M:SS", () => {
    expect(formatDuration(60_000)).toBe("1:00");
    expect(formatDuration(125_000)).toBe("2:05");
  });

  it("returns em-dash for empty duration", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(0)).toBe("—");
  });

  it("formats percent with locale", () => {
    expect(formatPercent(12.5, "en")).toBe("12.5%");
    expect(formatPercent(null, "en")).toBe("—");
  });
});
