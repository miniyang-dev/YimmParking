import { ageMinutes } from "./availability";
import type { Phrase } from "./insight";
import type { CurbSegment } from "./types";

/** What the count cell says; like the lot cell, zero, no data and a count stay distinct. */
export type CurbCell = { kind: "count"; available: number } | { kind: "full" } | { kind: "none" };

export function curbCell(segment: CurbSegment): CurbCell {
  if (segment.available === null) return { kind: "none" };
  if (segment.available === 0 || segment.fullness === "full") return { kind: "full" };
  return { kind: "count", available: segment.available };
}

/** A count older than this says how old it is (New Taipei's often runs 15–20 minutes behind). */
export const CURB_OLD_AFTER_MIN = 15;

/** Short notes beside the count, in reading order. Nothing is said when all is ordinary. */
export function curbNotes(segment: CurbSegment, now: Date): Phrase[] {
  const notes: Phrase[] = [];
  // "Almost full" is the operator's view of the whole segment; once the car count is zero the cell
  // already says full, and saying both would contradict.
  const full = curbCell(segment).kind === "full";
  if (segment.fullness === "almost_full" && !full) notes.push({ key: "curb.almostFull" });
  if (segment.fullness === "overcrowded") notes.push({ key: "curb.overcrowded" });
  if (segment.service === "outside_hours") notes.push({ key: "curb.outsideHours" });
  if (segment.service === "resting") notes.push({ key: "curb.resting" });
  if (segment.service === "suspended") notes.push({ key: "curb.suspended" });
  if (segment.space_kind === "all" && segment.available !== null) notes.push({ key: "curb.allTypes" });
  const age = ageMinutes(segment.observed_at, now);
  if (segment.available !== null && age !== null && age > CURB_OLD_AFTER_MIN) {
    notes.push({ key: "curb.age", vars: { min: age } });
  }
  return notes;
}
