import type { Phrase } from "./insight";
import type { Lot } from "./types";

/** The headline hourly rate, or "fee unknown": never a guessed number. */
export function feePhrase(lot: Lot): Phrase {
  return lot.hourly_rate !== null
    ? { key: "fee.perHour", vars: { rate: lot.hourly_rate } }
    : { key: "fee.unknown" };
}
