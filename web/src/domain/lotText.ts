import type { Phrase } from "./insight";
import type { Lot } from "./types";

/**
 * Opening hours as the feeds write them ("00:00:00-23:59:59"): seconds dropped, and a full day
 * said as such.
 */
export function formatServiceTime(raw: string): string {
  const text = raw.trim().replace(/(\d{1,2}:\d{2}):\d{2}/g, "$1");
  return /^0?0:00\s*[-~–]\s*(23:59|24:00)$/.test(text) ? "24 小時" : text;
}

/** The headline hourly rate, or "fee unknown": never a guessed number. */
export function feePhrase(lot: Lot): Phrase {
  return lot.hourly_rate !== null
    ? { key: "fee.perHour", vars: { rate: lot.hourly_rate } }
    : { key: "fee.unknown" };
}
