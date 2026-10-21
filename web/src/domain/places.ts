/**
 * Places the person searches from: the ones they starred, then the most recent others.
 *
 * Each keeps its coordinates, so going back to one is a free nearby search instead of a paid
 * address lookup. Places closer than about 11 m (4 decimals) are the same place.
 */
export interface SavedPlace {
  id: string;
  /** The address or label the search showed. */
  label: string;
  /** The person's own name for it ("家", "公司"), or null. */
  name: string | null;
  lat: number;
  lng: number;
  favorite: boolean;
  /** Last time it was searched from, ms since epoch. */
  usedAt: number;
}

export const MAX_RECENT = 8;
export const MAX_FAVORITES = 20;
export const MAX_NAME = 20;

export function placeId(lat: number, lng: number): string {
  return `${lat.toFixed(4)},${lng.toFixed(4)}`;
}

export function displayName(place: SavedPlace): string {
  return place.name ?? place.label;
}

/** Favourites first (most recently used first), then the rest by recency. */
export function ordered(places: readonly SavedPlace[]): SavedPlace[] {
  const byUse = (a: SavedPlace, b: SavedPlace) => b.usedAt - a.usedAt;
  return [
    ...places.filter((p) => p.favorite).sort(byUse),
    ...places.filter((p) => !p.favorite).sort(byUse),
  ];
}

function trimmed(places: SavedPlace[]): SavedPlace[] {
  const list = ordered(places);
  const favorites = list.filter((p) => p.favorite).slice(0, MAX_FAVORITES);
  const recent = list.filter((p) => !p.favorite).slice(0, MAX_RECENT);
  return [...favorites, ...recent];
}

/** Record a search from this place: added, or moved to the top with its newest label. */
export function remember(
  places: readonly SavedPlace[],
  where: { label: string; lat: number; lng: number },
  now: number,
): SavedPlace[] {
  const label = where.label.trim();
  if (!label || !Number.isFinite(where.lat) || !Number.isFinite(where.lng)) return [...places];
  const id = placeId(where.lat, where.lng);
  const existing = places.find((p) => p.id === id);
  const updated: SavedPlace = existing
    ? { ...existing, label, usedAt: now }
    : { id, label, name: null, lat: where.lat, lng: where.lng, favorite: false, usedAt: now };
  return trimmed([updated, ...places.filter((p) => p.id !== id)]);
}

export function toggleFavorite(places: readonly SavedPlace[], id: string): SavedPlace[] {
  return trimmed(places.map((p) => (p.id === id ? { ...p, favorite: !p.favorite } : p)));
}

/** A blank name goes back to showing the address. */
export function rename(places: readonly SavedPlace[], id: string, name: string): SavedPlace[] {
  const clean = name.trim().slice(0, MAX_NAME) || null;
  return places.map((p) => (p.id === id ? { ...p, name: clean } : p));
}

export function forget(places: readonly SavedPlace[], id: string): SavedPlace[] {
  return places.filter((p) => p.id !== id);
}

/** Turn a stored value back into a valid list; anything unreadable is dropped, never guessed. */
export function sanitizePlaces(value: unknown): SavedPlace[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const out: SavedPlace[] = [];
  for (const item of value as unknown[]) {
    const p = item as Partial<SavedPlace> | null;
    if (
      !p ||
      typeof p.label !== "string" ||
      !p.label.trim() ||
      typeof p.lat !== "number" ||
      typeof p.lng !== "number" ||
      !Number.isFinite(p.lat) ||
      !Number.isFinite(p.lng)
    ) {
      continue;
    }
    const id = placeId(p.lat, p.lng);
    if (seen.has(id)) continue;
    seen.add(id);
    out.push({
      id,
      label: p.label,
      name: typeof p.name === "string" && p.name.trim() ? p.name.trim().slice(0, MAX_NAME) : null,
      lat: p.lat,
      lng: p.lng,
      favorite: p.favorite === true,
      usedAt: typeof p.usedAt === "number" && Number.isFinite(p.usedAt) ? p.usedAt : 0,
    });
  }
  return trimmed(out);
}
