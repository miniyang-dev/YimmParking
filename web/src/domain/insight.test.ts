import { describe, expect, it } from "vitest";
import { clockOf, hoursPhrase, niceMax, taipeiSlot, trendPhrases } from "./insight";

const trend = (direction: "filling" | "emptying" | "steady", delta: number, full: number | null = null) => ({
  minutes: 30,
  delta,
  direction,
  full_in_min: full,
});

describe("trendPhrases", () => {
  it("says how many went and, when it can, when it will be full", () => {
    expect(trendPhrases(trend("filling", -12, 45), { quiet: true })).toEqual([
      { key: "trend.filling", vars: { min: 30, n: 12 } },
      { key: "trend.fullIn", vars: { min: 45 } },
    ]);
    expect(trendPhrases(trend("filling", -4), { quiet: true })).toHaveLength(1);
  });

  it("keeps the list quiet when nothing moves, but the detail says so", () => {
    expect(trendPhrases(trend("steady", 1), { quiet: true })).toEqual([]);
    expect(trendPhrases(trend("steady", 1), { quiet: false })).toEqual([
      { key: "trend.steady", vars: { min: 30 } },
    ]);
  });

  it("says nothing without a trend", () => {
    expect(trendPhrases(null, { quiet: false })).toEqual([]);
  });

  it("reports spaces freeing up", () => {
    expect(trendPhrases(trend("emptying", 8), { quiet: true })).toEqual([
      { key: "trend.emptying", vars: { min: 30, n: 8 } },
    ]);
  });
});

describe("hoursPhrase", () => {
  it("warns only when closing soon or closed", () => {
    expect(hoursPhrase({ status: "closing_soon", opens_at: null, closes_at: "23:00" })).toEqual({
      key: "hours.closingSoon",
      vars: { time: "23:00" },
    });
    expect(hoursPhrase({ status: "closed", opens_at: "07:00", closes_at: null })).toEqual({
      key: "hours.closed",
      vars: { time: "07:00" },
    });
    for (const status of ["always", "open", "unknown"] as const) {
      expect(hoursPhrase({ status, opens_at: null, closes_at: null })).toBeNull();
    }
  });
});

describe("chart helpers", () => {
  it("formats half hours and finds the Taipei slot whatever the device zone", () => {
    expect(clockOf(450)).toBe("07:30");
    expect(clockOf(1440)).toBe("00:00");
    expect(taipeiSlot(new Date("2026-10-22T06:47:00Z"))).toBe(14 * 60 + 30); // 14:47 Taipei
  });

  it("rounds the axis top up to a clean number", () => {
    expect([3, 10, 11, 37, 180, 201, 950].map(niceMax)).toEqual([10, 10, 20, 50, 200, 500, 1000]);
  });
});
