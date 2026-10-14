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
  const ageMin = ageInMinutes(station.observed_at, now);
  if (ageMin !== null && ageMin > STALE_AFTER_MIN) {
    return { kind: "stale", rent: station.rent, ret: station.ret, ageMin };
  }
  return { kind: "known", rent: station.rent, ret: station.ret };
}

function ageInMinutes(observedAt: string | null, now: Date): number | null {
  if (!observedAt) return null;
  const then = new Date(observedAt).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.round((now.getTime() - then) / 60_000));
}

/** Compass bearing in degrees [0, 360) from `from` towards `to`. */
export function bearingDeg(
  from: { lat: number; lng: number },
  to: { lat: number; lng: number },
): number {
  const rad = Math.PI / 180;
  const phi1 = from.lat * rad;
  const phi2 = to.lat * rad;
  const dLambda = (to.lng - from.lng) * rad;
  const y = Math.sin(dLambda) * Math.cos(phi2);
  const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLambda);
  return ((Math.atan2(y, x) / rad) + 360) % 360;
}
