import { describe, expect, it } from "vitest";
import { ageMinutes, spaceState } from "./availability";
import { compassLabel } from "./compass";
import { formatDistance } from "./distance";
import { toSections } from "./grouping";
import { filterFood, ratingFloors } from "./food";
import { walkMinutes } from "./walk";
import type { Availability, FoodPlace, Lot } from "./types";

const av = (over: Partial<Availability>): Availability => ({
  state: "known",
  count: 10,
  observed_at: "2026-10-10T14:37:00Z",
  freshness: "fresh",
  suspect: false,
  ...over,
});

describe("spaceState", () => {
  it("treats a real zero as full, not as no data", () => {
    expect(spaceState(av({ count: 0 }))).toEqual({ kind: "full", stale: false });
  });
  it("says when a zero is an old reading", () => {
    expect(spaceState(av({ count: 0, freshness: "stale" }))).toEqual({ kind: "full", stale: true });
  });
  it("treats unknown as none even when freshness is fresh", () => {
    expect(spaceState(av({ state: "unknown", count: null }))).toEqual({ kind: "none" });
  });
  it("marks stale readings but keeps the count", () => {
    expect(spaceState(av({ count: 57, freshness: "stale" }))).toEqual({
      kind: "stale",
      count: 57,
      suspect: false,
    });
  });
  it("carries the suspect flag", () => {
    expect(spaceState(av({ count: 263, suspect: true }))).toMatchObject({ kind: "known", suspect: true });
  });
});

describe("ageMinutes", () => {
  it("rounds to whole minutes and never goes negative", () => {
    const now = new Date("2026-10-10T14:40:00Z");
    expect(ageMinutes("2026-10-10T14:37:00Z", now)).toBe(3);
    expect(ageMinutes("2026-10-10T14:45:00Z", now)).toBe(0);
    expect(ageMinutes(null, now)).toBeNull();
    expect(ageMinutes("not a date", now)).toBeNull();
  });
});

describe("compassLabel", () => {
  it.each([
    [0, "北"],
    [44, "東北"],
    [90, "東"],
    [202, "南"],
    [316, "西北"],
    [359, "北"],
  ])("bearing %i is %s", (deg, label) => {
    expect(compassLabel(deg, "zh")).toBe(label);
  });
  it("has English labels", () => {
    expect(compassLabel(135, "en")).toBe("SE");
  });
});

describe("distance", () => {
  it("formats metres and kilometres", () => {
    expect(formatDistance(191.4)).toBe("191 m");
    expect(formatDistance(1345)).toBe("1.3 km");
    expect(formatDistance(12_400)).toBe("12 km");
  });
});

describe("toSections", () => {
  const lot = (id: string, vendor: string | null, block: string): Lot =>
    ({ id, vendor, block }) as unknown as Lot;
  it("makes one section per vendor and keeps the server order", () => {
    const sections = toSections(
      [
        lot("a", "iparking_dodohome", "priority"),
        lot("b", "iparking_dodohome", "priority"),
        lot("c", "liantong", "priority"),
        lot("d", null, "other"),
      ],
      "tiered",
    );
    expect(sections.map((s) => [s.key, s.lots.map((l) => l.id)])).toEqual([
      ["iparking_dodohome", ["a", "b"]],
      ["liantong", ["c"]],
      ["other", ["d"]],
    ]);
  });
  it("puts a vendor's lots that spilled into the other list in that list", () => {
    const sections = toSections(
      [lot("a", "times", "priority"), lot("b", "times", "other"), lot("c", null, "other")],
      "tiered",
    );
    expect(sections.map((s) => [s.key, s.lots.map((l) => l.id)])).toEqual([
      ["times", ["a"]],
      ["other", ["b", "c"]],
    ]);
  });
  it("uses a single section in distance mode", () => {
    expect(toSections([lot("a", "times", "distance"), lot("d", null, "distance")], "distance"))
      .toHaveLength(1);
  });
  it("returns nothing for an empty list", () => {
    expect(toSections([], "tiered")).toEqual([]);
    expect(toSections([], "distance")).toEqual([]);
  });
});

describe("filterFood", () => {
  const place = (id: string, rating: number | null, count: number | null, d: number): FoodPlace =>
    ({ id, rating, user_rating_count: count, distance_m: d }) as unknown as FoodPlace;
  const places = [
    place("near-low", 3.8, 900, 100),
    place("mid-high", 4.5, 300, 400),
    place("far-top", 4.8, 2000, 900),
    place("unrated", null, null, 50),
    place("near-ok", 4.2, 50, 200),
  ];
  const ids = (list: FoodPlace[]) => list.map((p) => p.id);

  it("keeps everything, unrated included, when there is no floor", () => {
    expect(ids(filterFood(places, 0, "walk"))).toEqual([
      "unrated",
      "near-low",
      "near-ok",
      "mid-high",
      "far-top",
    ]);
  });
  it("applies the rating floor inclusively and drops unrated places", () => {
    expect(ids(filterFood(places, 4.5, "walk"))).toEqual(["mid-high", "far-top"]);
    expect(ids(filterFood(places, 4, "walk"))).toEqual(["near-ok", "mid-high", "far-top"]);
  });
  it("sorts by rating, then review count, then distance", () => {
    const tied = [place("a", 4.5, 10, 300), place("b", 4.5, 100, 800), place("c", 4.5, 100, 200)];
    expect(ids(filterFood(tied, 0, "rating"))).toEqual(["c", "b", "a"]);
  });
  it("does not mutate its input", () => {
    const copy = [...places];
    filterFood(places, 4.5, "rating");
    expect(places).toEqual(copy);
  });
});

describe("ratingFloors", () => {
  it("never offers a threshold below what the server already applied", () => {
    expect(ratingFloors(4)).toEqual([4, 4.3, 4.5]);
    expect(ratingFloors(4.3)).toEqual([4.3, 4.5]);
    expect(ratingFloors(4.5)).toEqual([4.5]);
    expect(ratingFloors(4.8)).toEqual([4.8]);
  });
});

describe("filterFood by walking time", () => {
  const place = (id: string, walk: number | null, d: number): FoodPlace =>
    ({ id, rating: 4.5, user_rating_count: 500, walk_seconds: walk, distance_m: d }) as unknown as FoodPlace;

  it("orders by real walking time, not straight-line distance", () => {
    const list = [place("near_but_far_to_walk", 1000, 300), place("far_but_quick", 400, 700)];
    expect(filterFood(list, 0, "walk").map((p) => p.id)).toEqual([
      "far_but_quick",
      "near_but_far_to_walk",
    ]);
  });

  it("puts places without a walking time last, by distance", () => {
    const list = [place("unrouted_near", null, 50), place("routed", 900, 800), place("unrouted_far", null, 400)];
    expect(filterFood(list, 0, "walk").map((p) => p.id)).toEqual([
      "routed",
      "unrouted_near",
      "unrouted_far",
    ]);
  });
});

describe("walkMinutes", () => {
  it("rounds to whole minutes with a floor of one", () => {
    expect(walkMinutes(1039)).toBe(17);
    expect(walkMinutes(20)).toBe(1);
    expect(walkMinutes(90)).toBe(2);
  });
});
