const ZH = ["北", "東北", "東", "東南", "南", "西南", "西", "西北"] as const;
const EN = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] as const;

/** Eight-sector compass label for a bearing in degrees (0 = north, clockwise). */
export function compassLabel(bearingDeg: number, locale: "zh" | "en"): string {
  const normalized = ((bearingDeg % 360) + 360) % 360;
  const index = Math.floor((normalized + 22.5) / 45) % 8;
  return (locale === "zh" ? ZH : EN)[index] as string;
}
