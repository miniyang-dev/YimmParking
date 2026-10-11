import { describe, expect, it } from "vitest";
import {
  DEFAULT_PREFS,
  MAX_SHOW,
  moveVendor,
  sanitizePrefs,
  serializePrefs,
  setShow,
  VENDOR_KEYS,
} from "./vendors";

describe("vendor preferences", () => {
  it("defaults to every large vendor in order, two each", () => {
    expect(serializePrefs(DEFAULT_PREFS)).toBe(
      "iparking_dodohome:2,dodohome:2,liantong:2,times:2,uspace:2",
    );
  });

  it("moves a vendor up or down and leaves the ends alone", () => {
    const moved = moveVendor(DEFAULT_PREFS, 2, -1);
    expect(moved.map((p) => p.key)).toEqual([
      "iparking_dodohome",
      "liantong",
      "dodohome",
      "times",
      "uspace",
    ]);
    expect(moveVendor(DEFAULT_PREFS, 0, -1)).toBe(DEFAULT_PREFS);
    expect(moveVendor(DEFAULT_PREFS, VENDOR_KEYS.length - 1, 1)).toBe(DEFAULT_PREFS);
  });

  it("keeps the count between zero and the maximum", () => {
    expect(setShow(DEFAULT_PREFS, "times", 99).find((p) => p.key === "times")?.show).toBe(MAX_SHOW);
    expect(setShow(DEFAULT_PREFS, "times", -3).find((p) => p.key === "times")?.show).toBe(0);
    expect(setShow(DEFAULT_PREFS, "times", 0)).not.toBe(DEFAULT_PREFS);
  });

  it("reads back a stored list, dropping names that are not configurable", () => {
    const stored = [
      { key: "liantong", show: 4 },
      { key: "和停", show: 2 },
      { key: "liantong", show: 1 },
      { key: "dodohome", show: 99 },
    ];
    expect(sanitizePrefs(stored)).toEqual([
      { key: "liantong", show: 4 },
      { key: "dodohome", show: MAX_SHOW },
      { key: "iparking_dodohome", show: 0 },
      { key: "times", show: 0 },
      { key: "uspace", show: 0 },
    ]);
  });

  it("falls back to the defaults for anything unreadable", () => {
    expect(sanitizePrefs(null)).toBe(DEFAULT_PREFS);
    expect(sanitizePrefs("liantong")).toBe(DEFAULT_PREFS);
    expect(sanitizePrefs([{ key: "和停", show: 2 }])).toBe(DEFAULT_PREFS);
  });
});
