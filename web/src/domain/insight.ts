import type { StringKey } from "../i18n/strings";
import type { Lot } from "./types";

type Trend = NonNullable<Lot["trend"]>;
type Hours = Lot["hours"];
type Doubt = Lot["doubts"][number];

/** A message key and its values, so the wording stays in the string tables. */
export interface Phrase {
  key: StringKey;
  vars?: Record<string, string | number>;
}

/**
 * What the lot's recent movement says, most important first. "Steady" is only worth saying in
 * the detail view; the list stays quiet unless something is moving.
 */
export function trendPhrases(trend: Trend | null, { quiet }: { quiet: boolean }): Phrase[] {
  if (!trend) return [];
  const minutes = trend.minutes;
  switch (trend.direction) {
    case "filling": {
      const out: Phrase[] = [{ key: "trend.filling", vars: { min: minutes, n: -trend.delta } }];
      if (trend.full_in_min !== null) out.push({ key: "trend.fullIn", vars: { min: trend.full_in_min } });
      return out;
    }
    case "emptying":
      return [{ key: "trend.emptying", vars: { min: minutes, n: trend.delta } }];
    case "steady":
      return quiet ? [] : [{ key: "trend.steady", vars: { min: minutes } }];
  }
}

/** A short warning about opening hours, or null when there is nothing to warn about. */
export function hoursPhrase(hours: Hours): Phrase | null {
  if (hours.status === "closing_soon" && hours.closes_at) {
    return { key: "hours.closingSoon", vars: { time: hours.closes_at } };
  }
  if (hours.status === "closed" && hours.opens_at) {
    return { key: "hours.closed", vars: { time: hours.opens_at } };
  }
  return null;
}

export const DOUBT_SHORT: Record<Doubt, StringKey> = {
  frozen: "doubt.frozen.short",
  over_capacity: "doubt.over_capacity.short",
  often_missing: "doubt.often_missing.short",
};

export const DOUBT_LONG: Record<Doubt, StringKey> = {
  frozen: "doubt.frozen",
  over_capacity: "doubt.over_capacity",
  often_missing: "doubt.often_missing",
};

/** "07:30" for minutes after midnight. */
export function clockOf(minute: number): string {
  const m = ((minute % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

/** Minutes after midnight, Taipei time, rounded down to the half hour. */
export function taipeiSlot(now: Date, slotMinutes = 30): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Taipei",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  const minute = get("hour") * 60 + get("minute");
  return minute - (minute % slotMinutes);
}

/** A round top for the y axis: 10, 20, 50, 100, 200, 500… at or above the largest value. */
export function niceMax(value: number): number {
  if (value <= 10) return 10;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 5, 10]) if (step * power >= value) return step * power;
  return 10 * power;
}
