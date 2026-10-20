import type { Availability } from "./types";

/**
 * What the spaces cell should say. These states must stay distinguishable without colour:
 * "full" (a real zero) is a different fact from "none" (no data) and from "stale".
 */
export type SpaceState =
  | { kind: "known"; count: number; suspect: boolean }
  | { kind: "stale"; count: number; suspect: boolean }
  | { kind: "full"; stale: boolean }
  | { kind: "none" };

export function spaceState(a: Availability): SpaceState {
  if (a.state !== "known" || a.count === null) return { kind: "none" };
  // An old zero is still said to be old: a lot that was full half an hour ago may not be now.
  if (a.count === 0) return { kind: "full", stale: a.freshness === "stale" };
  if (a.freshness === "stale") return { kind: "stale", count: a.count, suspect: a.suspect };
  return { kind: "known", count: a.count, suspect: a.suspect };
}

export function ageMinutes(observedAt: string | null, now: Date): number | null {
  if (!observedAt) return null;
  const then = new Date(observedAt).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.round((now.getTime() - then) / 60_000));
}
