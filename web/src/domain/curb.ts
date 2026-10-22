import type { StringKey } from "../i18n/strings";
import type { CurbSegment } from "./types";

/** What the count cell says; like the lot cell, zero, no data and a count stay distinct. */
export type CurbCell = { kind: "count"; available: number } | { kind: "full" } | { kind: "none" };

export function curbCell(segment: CurbSegment): CurbCell {
  if (segment.available === null) return { kind: "none" };
  if (segment.available === 0 || segment.fullness === "full") return { kind: "full" };
  return { kind: "count", available: segment.available };
}

/** Short notes beside the count, in reading order. Nothing is said when all is ordinary. */
export function curbNotes(segment: CurbSegment): StringKey[] {
  const notes: StringKey[] = [];
  if (segment.fullness === "almost_full") notes.push("curb.almostFull");
  if (segment.fullness === "overcrowded") notes.push("curb.overcrowded");
  if (segment.service === "outside_hours") notes.push("curb.outsideHours");
  if (segment.service === "resting") notes.push("curb.resting");
  if (segment.service === "suspended") notes.push("curb.suspended");
  if (segment.space_kind === "all" && segment.available !== null) notes.push("curb.allTypes");
  return notes;
}
