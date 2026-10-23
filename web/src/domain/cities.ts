import type { StringKey } from "../i18n/strings";
import type { Lot, SearchResponse } from "./types";

export type CityKey = Lot["city"];
export type StaleSource = SearchResponse["meta"]["stale_sources"][number];

export const CITY_LABEL: Record<CityKey, StringKey> = {
  taipei: "city.taipei",
  new_taipei: "city.new_taipei",
};

/**
 * The stopped feeds worth mentioning for this list: only cities that have a lot in it, so a
 * search in New Taipei does not warn about Taipei.
 */
export function staleForList(stale: readonly StaleSource[], lots: readonly Lot[]): StaleSource[] {
  const cities = new Set(lots.map((lot) => lot.city));
  return stale.filter((source) => cities.has(source.city));
}

/** Cities whose counts in this list come from TDX (their own feed has stopped), in list order. */
export function tdxCities(lots: readonly Lot[]): CityKey[] {
  const out: CityKey[] = [];
  for (const lot of lots) {
    if (lot.availability.source === "tdx" && !out.includes(lot.city)) out.push(lot.city);
  }
  return out;
}

/** "10/19 10:26" in Taipei time, whatever the device's own zone. */
export function taipeiTime(iso: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Taipei",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("month")}/${part("day")} ${part("hour")}:${part("minute")}`;
}
