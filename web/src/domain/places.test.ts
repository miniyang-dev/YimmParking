import { describe, expect, it } from "vitest";
import {
  MAX_RECENT,
  displayName,
  forget,
  ordered,
  remember,
  rename,
  sanitizePlaces,
  toggleFavorite,
  type SavedPlace,
} from "./places";

const at = (label: string, lat: number, lng = 121.5) => ({ label, lat, lng });

describe("remember", () => {
  it("adds a place and moves a repeated one to the top with its newest label", () => {
    let list = remember([], at("市府路1號", 25.04), 1);
    list = remember(list, at("松高路11號", 25.05), 2);
    list = remember(list, at("臺北市政府", 25.04000001), 3); // the same place, within 11 m
    expect(list.map((p) => p.label)).toEqual(["臺北市政府", "松高路11號"]);
  });

  it("keeps only the most recent non-starred places", () => {
    let list: SavedPlace[] = [];
    for (let i = 0; i < MAX_RECENT + 3; i += 1) list = remember(list, at(`p${i}`, 25 + i / 100), i);
    expect(list).toHaveLength(MAX_RECENT);
    expect(list[0]?.label).toBe(`p${MAX_RECENT + 2}`);
  });

  it("never pushes a starred place out", () => {
    let list = toggleFavorite(remember([], at("家", 25.0), 0), "25.0000,121.5000");
    for (let i = 1; i <= MAX_RECENT + 3; i += 1) list = remember(list, at(`p${i}`, 25 + i / 100), i);
    expect(list.filter((p) => p.favorite).map((p) => p.label)).toEqual(["家"]);
    expect(list).toHaveLength(MAX_RECENT + 1);
  });

  it("ignores a place without a label or a coordinate", () => {
    expect(remember([], at("  ", 25), 1)).toEqual([]);
    expect(remember([], { label: "x", lat: Number.NaN, lng: 121 }, 1)).toEqual([]);
  });
});

describe("favourites and names", () => {
  const base = remember(remember([], at("A", 25.01), 1), at("B", 25.02), 2);

  it("lists starred places first", () => {
    const list = toggleFavorite(base, "25.0100,121.5000");
    expect(ordered(list).map((p) => p.label)).toEqual(["A", "B"]);
  });

  it("shows the person's name instead of the address, and a blank name restores it", () => {
    const named = rename(base, "25.0100,121.5000", "  家  ");
    const home = named.find((p) => p.label === "A") as SavedPlace;
    expect(displayName(home)).toBe("家");
    const cleared = rename(named, "25.0100,121.5000", " ");
    expect(displayName(cleared.find((p) => p.label === "A") as SavedPlace)).toBe("A");
  });

  it("forgets a place", () => {
    expect(forget(base, "25.0100,121.5000").map((p) => p.label)).toEqual(["B"]);
  });
});

describe("sanitizePlaces", () => {
  it("keeps readable entries and drops the rest", () => {
    const stored = [
      { label: "A", lat: 25.01, lng: 121.5, favorite: true, usedAt: 5, name: "家" },
      { label: "", lat: 25.02, lng: 121.5 },
      { label: "C", lat: "25", lng: 121.5 },
      { label: "A again", lat: 25.01, lng: 121.5 },
      null,
      "junk",
    ];
    const list = sanitizePlaces(stored);
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({ label: "A", name: "家", favorite: true, usedAt: 5 });
  });

  it("treats anything but a list as nothing saved", () => {
    expect(sanitizePlaces({})).toEqual([]);
    expect(sanitizePlaces(null)).toEqual([]);
  });
});
