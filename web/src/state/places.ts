import { useSyncExternalStore } from "react";
import { sanitizePlaces, type SavedPlace } from "../domain/places";

/**
 * Starred and recent places live in this browser only, like the vendor settings: the server
 * never sees them.
 */
const KEY = "yimm.places.v1";
const EVENT = "yimm:places";
const NONE: SavedPlace[] = [];

function load(): SavedPlace[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw === null ? NONE : sanitizePlaces(JSON.parse(raw));
  } catch {
    // Private windows and blocked storage throw; the app still works without the list.
    return NONE;
  }
}

let current: SavedPlace[] | null = null;

function getPlaces(): SavedPlace[] {
  current ??= load();
  return current;
}

/** Apply a change to the saved list (`update` gets the current list and returns the new one). */
export function updatePlaces(update: (places: SavedPlace[]) => SavedPlace[]): void {
  current = update(getPlaces());
  try {
    window.localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Not persisted, but still in effect for this page view.
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  return () => window.removeEventListener(EVENT, onChange);
}

export function usePlaces(): SavedPlace[] {
  return useSyncExternalStore(subscribe, getPlaces, () => NONE);
}
