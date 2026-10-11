import { compassLabel } from "../../domain/compass";
import { formatDistance } from "../../domain/distance";
import { walkMinutes } from "../../domain/walk";
import { toSections, type SectionKey } from "../../domain/grouping";
import type { Lot, SortMode } from "../../domain/types";
import { BRAND_LABEL, VENDOR_LABEL, type VendorKey } from "../../domain/vendors";
import { useI18n } from "../../i18n";
import type { StringKey } from "../../i18n/strings";
import { SpaceCell } from "../../ui/SpaceCell";
import { Symbol, type SymbolKind } from "../../ui/Symbol";

function sectionLabel(key: SectionKey): StringKey {
  if (key === "other") return "group.other";
  if (key === "distance") return "group.distance";
  return VENDOR_LABEL[key as VendorKey];
}

/** Vendor sections share one band style; the other two have their own. */
function bandClass(key: SectionKey): string {
  return key === "other" || key === "distance" ? `band--${key}` : "band--priority";
}

export function symbolFor(lot: Lot): SymbolKind {
  if (lot.vendor === "iparking_dodohome") return "iparking";
  if (lot.vendor) return "circle";
  return "cross";
}

export function feeHeadline(lot: Lot, t: ReturnType<typeof useI18n>["t"]): string {
  return lot.hourly_rate !== null ? t("fee.perHour", { rate: lot.hourly_rate }) : t("fee.unknown");
}

interface Props {
  lots: Lot[];
  mode: SortMode;
  now: Date;
  /** Lots inside the radius; only a shortlist is shown. */
  poolSize: number;
  /** Where the walking times came from. */
  walking: "google" | "quota_exhausted" | "unavailable";
  onOpen: (lot: Lot) => void;
}

export function ResultSheet({ lots, mode, now, poolSize, walking, onOpen }: Props) {
  const { t, locale } = useI18n();
  const sections = toSections(lots, mode);
  const routedCount = lots.filter((lot) => lot.walk_seconds !== null).length;
  let index = 0;

  return (
    <div className="sheet">
      <p className="sheet__note">
        {t("list.shown", { shown: lots.length, pool: poolSize })}
        {routedCount > 0 && <span> · {t("list.routed", { n: routedCount })}</span>}
        {walking === "quota_exhausted" && <span> · {t("walk.quota")}</span>}
        {walking === "unavailable" && <span> · {t("walk.unavailable")}</span>}
      </p>
      {sections.map((section) => (
        <section key={section.key} aria-labelledby={`band-${section.key}`}>
          <h2 id={`band-${section.key}`} className={`band ${bandClass(section.key)}`}>
            <span>{t(sectionLabel(section.key))}</span>
            <small>{t("group.count", { n: section.lots.length })}</small>
          </h2>
          <table className="lots">
            <thead className="sr-only">
              <tr>
                <th>{t("col.no")}</th>
                <th>{t("col.symbol")}</th>
                <th>{t("col.lot")}</th>
                <th>{t("col.spaces")}</th>
              </tr>
            </thead>
            <tbody>
              {section.lots.map((lot) => {
                index += 1;
                return (
                  <tr key={lot.id} className="lots__row" onClick={() => onOpen(lot)}>
                    <td className="lots__no">{index}</td>
                    <td className="lots__sym">
                      <Symbol kind={symbolFor(lot)} />
                    </td>
                    <td className="lots__main">
                      <button type="button" className="lots__open">
                        {lot.name}
                      </button>
                      <div className="lots__meta">
                        {lot.walk_seconds !== null ? (
                          <>
                            <b>{t("walk.min", { min: walkMinutes(lot.walk_seconds) })}</b>
                            <span>
                              {t("walk.straight", { d: formatDistance(lot.distance_m) })}{" "}
                              {compassLabel(lot.bearing_deg, locale)}
                            </span>
                          </>
                        ) : (
                          <b>
                            {t("walk.straight", { d: formatDistance(lot.distance_m) })}{" "}
                            {compassLabel(lot.bearing_deg, locale)}
                          </b>
                        )}
                        <span>{feeHeadline(lot, t)}</span>
                        {lot.brand !== "other" && (
                          <span className="lots__brand">
                            {lot.iparking ? `${t("brand.iparking")} ` : ""}
                            {t(BRAND_LABEL[lot.brand])}
                            {lot.brand_evidence === "phone" ? " *" : ""}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="lots__spaces">
                      <SpaceCell availability={lot.availability} now={now} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}

export function SheetSkeleton() {
  return (
    <div className="sheet" aria-hidden="true">
      <div className="band band--priority">
        <span className="skeleton skeleton--text" />
      </div>
      {Array.from({ length: 6 }, (_, i) => (
        <div className="lots__row lots__row--skeleton" key={i}>
          <span className="skeleton skeleton--box" />
          <span className="skeleton skeleton--line" />
          <span className="skeleton skeleton--cell" />
        </div>
      ))}
    </div>
  );
}

export function Legend() {
  const { t } = useI18n();
  const rows: { sym: SymbolKind; key: StringKey }[] = [
    { sym: "start", key: "legend.start" },
    { sym: "iparking", key: "legend.iparking" },
    { sym: "circle", key: "legend.circle" },
    { sym: "cross", key: "legend.cross" },
  ];
  return (
    <section className="legend" aria-labelledby="legend-title">
      <h2 id="legend-title" className="legend__title">
        {t("legend.title")}
      </h2>
      <ul className="legend__list">
        {rows.map((row) => (
          <li key={row.key}>
            <Symbol kind={row.sym} size={22} />
            <span>{t(row.key)}</span>
          </li>
        ))}
        <li>
          <span className="swatch swatch--stale" aria-hidden="true" />
          <span>{t("legend.stale")}</span>
        </li>
        <li>
          <span className="swatch swatch--full" aria-hidden="true" />
          <span>{t("legend.full")}</span>
        </li>
        <li>
          <span className="swatch swatch--none" aria-hidden="true" />
          <span>{t("legend.none")}</span>
        </li>
        <li>
          <span>{t("legend.byPhone")}</span>
        </li>
      </ul>
    </section>
  );
}
