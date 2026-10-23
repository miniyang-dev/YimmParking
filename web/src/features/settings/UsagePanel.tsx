import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { USAGE_LABEL, usagePercent } from "../../domain/usage";
import { useI18n } from "../../i18n";

/** This month's usage as percentages of each limit. Read from the server; costs nothing to fetch. */
export function UsagePanel() {
  const { t } = useI18n();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    staleTime: 60_000,
    retry: 1,
  });

  return (
    <section className="usage" aria-labelledby="usage-title">
      <h3 id="usage-title" className="usage__title">
        {t("usage.title")}
      </h3>

      {health.isError && <p className="usage__note">{t("usage.unavailable")}</p>}

      {health.data && (
        <ul className="usage__list">
          {health.data.usage.map((item) => {
            const key = USAGE_LABEL[item.meter];
            if (!key) return null;
            const label = t(key);
            const percent = usagePercent(item.used, item.limit);
            return (
              <li key={item.meter} className="usage__row">
                <span className="usage__label">{label}</span>
                <span
                  className="usage__meter"
                  role="meter"
                  aria-label={t("usage.bar", { label, p: percent.toFixed(1) })}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={percent}
                >
                  <span className="usage__fill" style={{ width: `${percent}%` }} />
                </span>
                <span className="usage__value">{percent.toFixed(1)}%</span>
              </li>
            );
          })}
        </ul>
      )}

      <p className="usage__note">{t("usage.note")}</p>
      {health.data?.usage.some((item) => item.meter === "tdx") && (
        <p className="usage__note">{t("usage.tdxNote")}</p>
      )}
    </section>
  );
}
