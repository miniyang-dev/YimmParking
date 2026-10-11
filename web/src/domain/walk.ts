/** Whole minutes for display; a walk of any length reads as at least one minute. */
export function walkMinutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}
