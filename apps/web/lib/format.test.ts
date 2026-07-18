import { describe, expect, it } from "vitest";
import { formatDuration, formatUsd, formatPercent, formatDateTime } from "./format";

describe("formatDuration", () => {
  it("formats seconds as m:ss", () => {
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(5)).toBe("0:05");
    expect(formatDuration(600)).toBe("10:00");
  });

  it("returns a dash for null/undefined", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });
});

describe("formatUsd", () => {
  it("formats a numeric string as USD currency", () => {
    expect(formatUsd("1.5")).toContain("1,50");
  });

  it("falls back to zero for missing/invalid values", () => {
    expect(formatUsd(null)).toBe("$0,00");
    expect(formatUsd("not-a-number")).toBe("$0,00");
  });
});

describe("formatPercent", () => {
  it("formats a 0-1 ratio as a percentage", () => {
    expect(formatPercent(0.25)).toContain("25");
  });

  it("returns a dash for null/undefined", () => {
    expect(formatPercent(null)).toBe("—");
  });
});

describe("formatDateTime", () => {
  it("returns a dash for invalid or missing input", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("not-a-date")).toBe("—");
  });

  it("formats a valid ISO timestamp", () => {
    expect(formatDateTime("2026-07-18T10:00:00Z")).not.toBe("—");
  });
});
