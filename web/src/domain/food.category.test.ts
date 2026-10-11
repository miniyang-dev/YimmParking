import { describe, expect, it } from "vitest";
import { categoryCounts, inCategory } from "./food";
import type { FoodPlace } from "./types";

const place = (id: string, category: string) => ({ id, category }) as unknown as FoodPlace;

describe("food categories", () => {
  const places = [place("a", "chinese"), place("b", "cafe"), place("c", "chinese"), place("d", "other")];

  it("counts only the categories that are present, in display order", () => {
    expect(categoryCounts(places)).toEqual([
      { key: "chinese", count: 2 },
      { key: "cafe", count: 1 },
      { key: "other", count: 1 },
    ]);
  });

  it("returns everything for All and only the chosen category otherwise", () => {
    expect(inCategory(places, null).map((p) => p.id)).toEqual(["a", "b", "c", "d"]);
    expect(inCategory(places, "chinese").map((p) => p.id)).toEqual(["a", "c"]);
    expect(inCategory(places, "western")).toEqual([]);
  });
});
