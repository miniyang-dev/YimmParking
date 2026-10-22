import { ageMinutes } from "./availability";
import type { BikeStation } from "./types";

/** A reading older than this is shown as old, with its age, instead of as a plain number. */
export const STALE_AFTER_MIN = 10;

/**
 * What a station's "bikes to take" cell should say. Like the lot spaces cell, the states stay
 * distinguishable without colour: a real zero is a different fact from "no reading" and from "old".
 */
export type BikeState =
  | { kind: "known"; rent: number; ret: number | null }
  | { kind: "stale"; rent: number; ret: number | null; ageMin: number }
  | { kind: "empty"; ret: number | null }
  | { kind: "none" };

export function bikeState(station: BikeStation, now: Date): BikeState {
  if (station.rent === null) return { kind: "none" };
  if (station.rent === 0) return { kind: "empty", ret: station.ret };
  const ageMin = ageMinutes(station.observed_at, now);
  if (ageMin !== null && ageMin > STALE_AFTER_MIN) {
    return { kind: "stale", rent: station.rent, ret: station.ret, ageMin };
  }
  return { kind: "known", rent: station.rent, ret: station.ret };
}
