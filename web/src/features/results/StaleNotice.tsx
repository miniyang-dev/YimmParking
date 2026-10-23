import { CITY_LABEL, staleForList, taipeiTime, tdxCities, type StaleSource } from "../../domain/cities";
import type { Lot } from "../../domain/types";
import { useI18n } from "../../i18n";

/**
 * Says when a city's feed has stopped, so a list full of "no data" reads as the source being
 * down, not as the app being broken or every lot being unknown.
 */
export function StaleNotice({ stale, lots }: { stale: readonly StaleSource[]; lots: readonly Lot[] }) {
  const { t } = useI18n();
  const shown = staleForList(stale, lots);
  const fallback = tdxCities(lots);
  if (shown.length === 0 && fallback.length === 0) return null;
  return (
    <div className="notice" role="status">
      {fallback.length > 0 && (
        <p>
          {t("source.tdxList", {
            city: fallback.map((city) => t(CITY_LABEL[city])).join(t("city.join")),
          })}
        </p>
      )}
      {shown.map((source) => {
        const city = t(CITY_LABEL[source.city]);
        return (
          <p key={source.city}>
            {source.as_of
              ? t("stale.since", { city, time: taipeiTime(source.as_of) })
              : t("stale.never", { city })}
          </p>
        );
      })}
    </div>
  );
}
