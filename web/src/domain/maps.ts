export interface Coordinate {
  lat: number;
  lng: number;
}

/**
 * A Google Maps directions link (the documented Maps URLs scheme; no API key, no billed call).
 *
 * `origin` is where the person is searching from, so the route starts there rather than at
 * whatever the maps app thinks "here" is. `placeId` lets Maps show the destination by name.
 */
export function directionsUrl(
  origin: Coordinate,
  destination: Coordinate,
  options: { placeId?: string | null; travelMode?: "driving" | "walking" } = {},
): string {
  const point = (c: Coordinate) => `${c.lat.toFixed(6)},${c.lng.toFixed(6)}`;
  const params = new URLSearchParams({
    api: "1",
    origin: point(origin),
    destination: point(destination),
  });
  if (options.placeId) params.set("destination_place_id", options.placeId);
  if (options.travelMode) params.set("travelmode", options.travelMode);
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}
