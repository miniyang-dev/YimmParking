import { ApiError } from "../../api/client";
import { CITY_LABEL } from "../../domain/cities";
import { curbCell, curbNotes } from "../../domain/curb";
import { formatDistance } from "../../domain/distance";
import type { Coordinate } from "../../domain/maps";
import type { CurbSegment } from "../../domain/types";
import { useI18n } from "../../i18n";
import { useCurb } from "../../state/queries";

export function CurbCountCell({ segment }: { segment: CurbSegment }) {
  const { t } = useI18n();
  const cell = curbCell(segment);
  const total = segment.total !== null ? t("curb.of", { n: segment.total }) : null;
  switch (cell.kind) {
    case "full":
      return (
        <div className="cell cell--full" role="group" aria-label={[t("curb.full"), total].filter(Boolean).join(", ")}>
          <b className="cell__num">{t("curb.full")}</b>
          {total && <span className="cell__sub">{total}</span>}
        </div>
      );
    case "none":
      return (
        <div className="cell cell--none" role="group" aria-label={t("curb.nodata")}>
          <b className="cell__word">{t("curb.nodata")}</b>
        </div>
      );
    case "count":
      return (
        <div
          className="cell"
          role="group"
          aria-label={[t("curb.left", { n: cell.available }), total].filter(Boolean).join(", ")}
        >
          <b className="cell__num">{cell.available}</b>
          {total && <span className="cell__sub">{total}</span>}
        </div>
      );
  }
}

interface Props {
  origin: Coordinate;
  now: Date;
  /** The segment shown in the detail beside the sheet (wide screens). */
  activeId?: string;
  onOpen: (segment: CurbSegment) => void;
}

/**
 * Metered street segments near the search origin, below the lot list; a row opens like a lot.
 * Hidden entirely while the server has no TDX credentials: an unconfigured source is not
 * something a driver can act on.
 */
export function CurbSection({ origin, now, activeId, onOpen }: Props) {
  const { t } = useI18n();
  const query = useCurb(origin.lat, origin.lng);

  if (query.isError && query.error instanceof ApiError && query.error.code === "curb_unconfigured") {
    return null;
  }
  if (query.isPending) {
    return (
      <section className="curb" aria-labelledby="curb-title" aria-busy="true">
        <h2 id="curb-title" className="band band--other">
          <span>{t("curb.loading")}</span>
        </h2>
      </section>
    );
  }
  if (query.isError) {
    return (
      <section className="curb" aria-labelledby="curb-title">
        <h2 id="curb-title" className="band band--other">
          <span>{t("curb.heading")}</span>
        </h2>
        <p className="note" role="status">
          {t("curb.error")}
        </p>
      </section>
    );
  }

  const { results, radius_m: radius, expanded, unavailable_cities: missing } = query.data;
  const names = missing.map((city) => t(CITY_LABEL[city])).join(t("city.join"));
  return (
    <section className="curb" aria-labelledby="curb-title">
      <h2 id="curb-title" className="band band--other">
        <span>{t("curb.title", { r: radius, n: results.length })}</span>
      </h2>
      {missing.length > 0 && (
        <p className="note" role="status">
          {t("curb.partial", { cities: names })}
        </p>
      )}
      {results.length === 0 ? (
        <p className="note">{t("curb.none", { r: radius })}</p>
      ) : (
        <>
          {expanded && <p className="note">{t("curb.expanded", { r: radius })}</p>}
          <table className="lots lots--curb">
            <tbody>
              {results.map((segment, i) => {
                const notes = curbNotes(segment, now);
                return (
                  <tr
                    key={segment.id}
                    className={segment.id === activeId ? "lots__row lots__row--active" : "lots__row"}
                    aria-current={segment.id === activeId ? "true" : undefined}
                    onClick={() => onOpen(segment)}
                  >
                    <td className="lots__no">{String.fromCharCode(97 + (i % 26))}</td>
                    <td className="lots__main">
                      <button type="button" className="lots__open">
                        {segment.name}
                      </button>
                      <div className="lots__meta">
                        <span>{t("walk.straight", { d: formatDistance(segment.distance_m) })}</span>
                        {segment.description && segment.description !== segment.name && (
                          <span>{segment.description}</span>
                        )}
                        {notes.map((note) => (
                          <span key={note.key} className="lots__hours">
                            {t(note.key, note.vars)}
                          </span>
                        ))}
                      </div>
                      {segment.fare && <div className="curb__fare">{segment.fare}</div>}
                    </td>
                    <td className="lots__spaces">
                      <CurbCountCell segment={segment} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
      <p className="attrib">{t("curb.note")}</p>
    </section>
  );
}
