import type { StringKey } from "../i18n/strings";

/**
 * The large operators the user can put first. Only these are configurable: a small operator
 * cannot be added, and the server refuses any other key.
 */
export const VENDOR_KEYS = ["iparking_dodohome", "dodohome", "liantong", "times", "uspace"] as const;
export type VendorKey = (typeof VENDOR_KEYS)[number];

export const DEFAULT_SHOW = 2;
export const MAX_SHOW = 8;

export interface VendorPick {
  key: VendorKey;
  show: number;
}

export type VendorPrefs = VendorPick[];

export const DEFAULT_PREFS: VendorPrefs = VENDOR_KEYS.map((key) => ({ key, show: DEFAULT_SHOW }));

export const VENDOR_LABEL: Record<VendorKey, StringKey> = {
  iparking_dodohome: "vendor.iparking_dodohome",
  dodohome: "vendor.dodohome",
  liantong: "vendor.liantong",
  times: "vendor.times",
  uspace: "vendor.uspace",
};

/** The brand label for a lot's own operator, shown in the lot row and detail. */
export const BRAND_LABEL: Record<"dodohome" | "liantong" | "times" | "uspace", StringKey> = {
  dodohome: "brand.dodohome",
  liantong: "brand.liantong",
  times: "brand.times",
  uspace: "brand.uspace",
};

function isVendorKey(value: unknown): value is VendorKey {
  return typeof value === "string" && (VENDOR_KEYS as readonly string[]).includes(value);
}

function clampShow(value: unknown): number {
  const n = typeof value === "number" ? Math.round(value) : Number.NaN;
  if (!Number.isFinite(n)) return DEFAULT_SHOW;
  return Math.min(MAX_SHOW, Math.max(0, n));
}

/**
 * Turn a stored value back into a valid list. Anything unreadable falls back to the default, and
 * a vendor missing from a readable list is appended with nothing shown, as the server does.
 */
export function sanitizePrefs(value: unknown): VendorPrefs {
  if (!Array.isArray(value)) return DEFAULT_PREFS;
  const seen = new Set<VendorKey>();
  const picks: VendorPrefs = [];
  for (const item of value as unknown[]) {
    const key = (item as { key?: unknown } | null)?.key;
    if (!isVendorKey(key) || seen.has(key)) continue;
    seen.add(key);
    picks.push({ key, show: clampShow((item as { show?: unknown }).show) });
  }
  if (picks.length === 0) return DEFAULT_PREFS;
  for (const key of VENDOR_KEYS) if (!seen.has(key)) picks.push({ key, show: 0 });
  return picks;
}

/** The `vendors` query value: `iparking_dodohome:2,dodohome:2,…`, in priority order. */
export function serializePrefs(prefs: VendorPrefs): string {
  return prefs.map((p) => `${p.key}:${p.show}`).join(",");
}

export function moveVendor(prefs: VendorPrefs, index: number, delta: -1 | 1): VendorPrefs {
  const target = index + delta;
  if (index < 0 || target < 0 || index >= prefs.length || target >= prefs.length) return prefs;
  const next = [...prefs];
  [next[index], next[target]] = [next[target] as VendorPick, next[index] as VendorPick];
  return next;
}

export function setShow(prefs: VendorPrefs, key: VendorKey, show: number): VendorPrefs {
  return prefs.map((p) => (p.key === key ? { key, show: clampShow(show) } : p));
}

export function samePrefs(a: VendorPrefs, b: VendorPrefs): boolean {
  return serializePrefs(a) === serializePrefs(b);
}
