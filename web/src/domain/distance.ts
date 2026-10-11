/** "191 m" below a kilometre, "1.3 km" above. Rounded for reading, never for ordering. */
export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  const km = meters / 1000;
  return `${km >= 10 ? Math.round(km) : km.toFixed(1)} km`;
}
