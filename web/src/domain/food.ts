import type { FoodPlace } from "./types";

/** Minimum star rating a place must have; 0 means no filter. */
export type RatingFloor = number;
export type FoodSort = "walk" | "rating";

const OPTIONAL_FLOORS = [4.3, 4.5] as const;

/**
 * The thresholds a person can pick. The server has already removed everything below
 * `applied`, so a lower choice would do nothing and is not offered; the applied floor itself is
 * the "show everything fetched" choice.
 */
export function ratingFloors(applied: number): RatingFloor[] {
  return [applied, ...OPTIONAL_FLOORS.filter((value) => value > applied)];
}

/**
 * Filter and order a result set that is already in memory. This never triggers a new request:
 * every fetch is billed, so changing the filter must not cost anything.
 *
 * A place with no rating is dropped by any rating floor rather than guessed at.
 */
export function filterFood(
  places: readonly FoodPlace[],
  floor: RatingFloor,
  sort: FoodSort,
): FoodPlace[] {
  const kept = places.filter((p) => floor === 0 || (p.rating !== null && p.rating >= floor));
  return [...kept].sort((a, b) => {
    if (sort === "rating") {
      const byRating = (b.rating ?? -1) - (a.rating ?? -1);
      if (byRating !== 0) return byRating;
      const byCount = (b.user_rating_count ?? 0) - (a.user_rating_count ?? 0);
      if (byCount !== 0) return byCount;
    }
    // Real walking time when the server has it; places without one go last, by distance.
    const walkA = a.walk_seconds ?? Number.POSITIVE_INFINITY;
    const walkB = b.walk_seconds ?? Number.POSITIVE_INFINITY;
    if (walkA !== walkB) return walkA < walkB ? -1 : 1;
    return a.distance_m - b.distance_m;
  });
}

/** The food categories, in the order they are offered. Mirrors the server's grouping. */
export const FOOD_CATEGORIES = [
  "chinese",
  "japanese",
  "korean",
  "thai",
  "southeast_asian",
  "western",
  "seafood",
  "cafe",
  "other",
] as const;
export type FoodCategoryKey = (typeof FOOD_CATEGORIES)[number];

/** Categories that have at least one place in the list, with how many, in display order. */
export function categoryCounts(places: readonly FoodPlace[]): { key: FoodCategoryKey; count: number }[] {
  return FOOD_CATEGORIES.flatMap((key) => {
    const count = places.filter((p) => p.category === key).length;
    return count > 0 ? [{ key, count }] : [];
  });
}

/** `null` means every category. */
export function inCategory(places: readonly FoodPlace[], category: FoodCategoryKey | null): FoodPlace[] {
  return category === null ? [...places] : places.filter((p) => p.category === category);
}
