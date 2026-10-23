import type { StringKey } from "../i18n/strings";

/**
 * Shown by what the visitor does, not by the provider's product name. An unknown meter is
 * dropped rather than shown raw.
 */
export const USAGE_LABEL: Record<string, StringKey> = {
  geocoding: "usage.address",
  places_nearby: "usage.food",
  routes_elements: "usage.walking",
  tdx: "usage.tdx",
};

/**
 * Percent of the monthly limit, to one decimal so a small share of a large limit still reads as
 * more than zero. Clamped to 0–100.
 */
export function usagePercent(used: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((used / limit) * 1000) / 10));
}
