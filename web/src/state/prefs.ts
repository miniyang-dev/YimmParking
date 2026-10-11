import { useSyncExternalStore } from "react";
import { DEFAULT_PREFS, sanitizePrefs, type VendorPrefs } from "../domain/vendors";

/**
 * The vendor order and counts are a per-viewer convenience, so they live in this browser only.
 * The server never stores them: each search carries them as a query parameter.
 */
const KEY = "yimm.vendors.v1";
const EVENT = "yimm:prefs";

function load(): VendorPrefs {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw === null ? DEFAULT_PREFS : sanitizePrefs(JSON.parse(raw));
  } catch {
    // Private windows and blocked storage throw; the defaults still work.
    return DEFAULT_PREFS;
  }
}

let current: VendorPrefs | null = null;

export function getPrefs(): VendorPrefs {
  current ??= load();
  return current;
}

export function savePrefs(next: VendorPrefs): void {
  current = next;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Not persisted, but still in effect for this page view.
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  return () => window.removeEventListener(EVENT, onChange);
}

export function usePrefs(): VendorPrefs {
  return useSyncExternalStore(subscribe, getPrefs, () => DEFAULT_PREFS);
}
