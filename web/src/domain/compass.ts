const ZH = ["北", "東北", "東", "東南", "南", "西南", "西", "西北"] as const;
const EN = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] as const;

/** Initial bearing from one point to another, in degrees (0 = north, clockwise). */
export function bearingDeg(
  from: { lat: number; lng: number },
  to: { lat: number; lng: number },
): number {
  const rad = Math.PI / 180;
  const φ1 = from.lat * rad;
  const φ2 = to.lat * rad;
  const Δλ = (to.lng - from.lng) * rad;
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return ((Math.atan2(y, x) / rad) + 360) % 360;
}

/** Eight-sector compass label for a bearing in degrees (0 = north, clockwise). */
export function compassLabel(bearingDeg: number, locale: "zh" | "en"): string {
  const normalized = ((bearingDeg % 360) + 360) % 360;
  const index = Math.floor((normalized + 22.5) / 45) % 8;
  return (locale === "zh" ? ZH : EN)[index] as string;
}
