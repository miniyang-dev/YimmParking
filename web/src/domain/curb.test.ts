import { describe, expect, it } from "vitest";
import { curbCell, curbNotes } from "./curb";
import type { CurbSegment } from "./types";

const seg = (over: Partial<CurbSegment>): CurbSegment => ({
  id: "taipei:1",
  name: "松高路",
  description: "",
  fare: "",
  town: "信義區",
  lat: 25.04,
  lng: 121.56,
  distance_m: 120,
  total: 20,
  available: 6,
  space_kind: "car",
  fullness: "available",
  service: "open",
  observed_at: null,
  ...over,
});

describe("curbCell", () => {
  it("keeps a count, a real zero and no data apart", () => {
    expect(curbCell(seg({ available: 6 }))).toEqual({ kind: "count", available: 6 });
    expect(curbCell(seg({ available: 0 }))).toEqual({ kind: "full" });
    expect(curbCell(seg({ available: null }))).toEqual({ kind: "none" });
  });

  it("trusts the operator's full flag over a stray count", () => {
    expect(curbCell(seg({ available: 2, fullness: "full" }))).toEqual({ kind: "full" });
  });
});

const NOW = new Date("2026-10-23T05:00:00Z");

describe("curbNotes", () => {
  it("says nothing when all is ordinary", () => {
    expect(curbNotes(seg({}), NOW)).toEqual([]);
  });

  it("names the operator's state and an all-types count", () => {
    const notes = curbNotes(seg({ fullness: "almost_full", service: "outside_hours", space_kind: "all" }), NOW);
    expect(notes.map((n) => n.key)).toEqual(["curb.almostFull", "curb.outsideHours", "curb.allTypes"]);
  });

  it("does not warn about an all-types count when there is no count", () => {
    expect(curbNotes(seg({ space_kind: "all", available: null }), NOW)).toEqual([]);
  });

  it("does not call a segment almost full when its car count is already zero", () => {
    expect(curbNotes(seg({ available: 0, fullness: "almost_full" }), NOW)).toEqual([]);
    expect(curbNotes(seg({ available: 3, fullness: "almost_full" }), NOW)).toEqual([
      { key: "curb.almostFull" },
    ]);
  });

  it("says how old a count is once it is over 15 minutes", () => {
    expect(curbNotes(seg({ observed_at: "2026-10-23T04:50:00Z" }), NOW)).toEqual([]);
    expect(curbNotes(seg({ observed_at: "2026-10-23T04:42:00Z" }), NOW)).toEqual([
      { key: "curb.age", vars: { min: 18 } },
    ]);
  });
});
