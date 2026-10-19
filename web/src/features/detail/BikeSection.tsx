import { bearingDeg, bikeState } from "../../domain/bikes";
import { formatDistance } from "../../domain/distance";
import { directionsUrl, type Coordinate } from "../../domain/maps";
import type { BikeResponse, BikeStation } from "../../domain/types";
import { useI18n } from "../../i18n";
import { useBikes } from "../../state/queries";
import { Symbol } from "../../ui/Symbol";

interface Props {
  /** The lot: distances are measured from it and every walking route starts at it. */
  lot: Coordinate;
  now: Date;
}

const FIRST_RADIUS_M = 400;

/** Two rings (400 m and the widened radius) with each station at its bearing. Direction only. */
function RingDiagram({ lot, stations, radius }: { lot: Coordinate; stations: BikeStation[]; radius: number }) {
  const c = 66;
  const outer = 58;
  const inner = (outer * FIRST_RADIUS_M) / radius;
  return (
    <svg className="bikes__rings" viewBox="0 0 132 132" aria-hidden="true">
      <circle cx={c} cy={c} r={inner} className="course__ring" />
      <circle cx={c} cy={c} r={outer} className="bikes__outer" />
      <path d="M66 2v8" className="course__north" />
      <path d="M66 58 73 71H59z" className="course__start" />
      {stations.map((s) => {
        const angle = (bearingDeg(lot, s) * Math.PI) / 180;
        const r = Math.min(outer - 6, (s.distance_m / radius) * outer);
        const x = c + Math.sin(angle) * r;
        const y = c - Math.cos(angle) * r;
        return <path key={s.id} d={`M${x} ${y - 5}l5 5-5 5-5-5z`} className="bikes__dot" />;
      })}
    </svg>
  );
}

function BikeCell({ station, now }: { station: BikeStation; now: Date }) {
  const { t } = useI18n();
  const state = bikeState(station, now);
  const ret = "ret" in state && state.ret !== null ? t("bikes.ret", { n: state.ret }) : null;

  switch (state.kind) {
    case "empty":
      return (
        <div className="cell cell--full" role="group" aria-label={t("bikes.empty")}>
          <b className="cell__word">{t("bikes.empty")}</b>
          {ret && <span className="cell__sub">{ret}</span>}
        </div>
      );
    case "none":
      return (
        <div className="cell cell--none" role="group" aria-label={t("bikes.none")}>
          <b className="cell__word">{t("bikes.none")}</b>
        </div>
      );
    case "stale":
    case "known": {
      const sub = state.kind === "stale" ? t("bikes.ago", { min: state.ageMin }) : ret;
      return (
        <div
          className={`cell ${state.kind === "stale" ? "cell--stale" : ""}`}
          role="group"
          aria-label={`${state.rent}${sub ? `, ${sub}` : ""}`}
        >
          <b className="cell__num">{state.rent}</b>
          {sub && <span className="cell__sub">{sub}</span>}
          {state.kind === "stale" && ret && <span className="cell__sub">{ret}</span>}
        </div>
      );
    }
  }
}

/** Said whenever a city's feed could not be read: a short or empty list is then not the whole answer. */
function MissingCities({ cities }: { cities: BikeResponse["unavailable_cities"] }) {
  const { t } = useI18n();
  if (cities.length === 0) return null;
  const names = cities.map((city) => t(`bikes.city.${city}`)).join(t("bikes.city.join"));
  return (
    <p className="note" role="status">
      {t("bikes.partial", { cities: names })}
    </p>
  );
}

function GoIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 19 19 5M8 5h11v11" />
    </svg>
  );
}

/** YouBike stations near the opened lot; each row opens walking directions from the lot. */
export function BikeSection({ lot, now }: Props) {
  const { t } = useI18n();
  const query = useBikes(lot.lat, lot.lng);

  if (query.isPending) {
    return (
      <section className="bikes" aria-labelledby="bikes-title" aria-busy="true">
        <h2 id="bikes-title" className="band band--other">
          <span>{t("bikes.loading")}</span>
        </h2>
        <div className="bikes__skeleton" aria-hidden="true">
          <span className="skeleton" />
          <span className="skeleton" />
        </div>
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className="bikes" aria-labelledby="bikes-title">
        <h2 id="bikes-title" className="band band--other">
          <span>{t("bikes.heading")}</span>
        </h2>
        <p className="note" role="status">
          {t("bikes.error")}
          <br />
          <button type="button" className="textbtn" onClick={() => void query.refetch()}>
            {t("bikes.retry")}
          </button>
        </p>
      </section>
    );
  }

  const { results, radius_m: radius, expanded, unavailable_cities: missing } = query.data;
  if (results.length === 0) {
    return (
      <section className="bikes" aria-labelledby="bikes-title">
        <h2 id="bikes-title" className="band band--other">
          <span>{t("bikes.title", { r: radius, n: 0 })}</span>
        </h2>
        <MissingCities cities={missing} />
        <p className="note" role="status">
          {t("bikes.noStation", { r: radius })}
          <small className="bikes__hint">{t("bikes.noStationHint", { r: radius })}</small>
        </p>
      </section>
    );
  }

  return (
    <section className="bikes" aria-labelledby="bikes-title">
      <h2 id="bikes-title" className="band band--other">
        <span>{t("bikes.title", { r: radius, n: results.length })}</span>
      </h2>
      <MissingCities cities={missing} />
      {expanded && (
        <div className="bikes__widened">
          <RingDiagram lot={lot} stations={results} radius={radius} />
          <div>
            <p className="bikes__widened-title">
              {t("bikes.expanded", { from: FIRST_RADIUS_M, to: radius })}
            </p>
            <p className="bikes__hint">{t("bikes.schematic")}</p>
          </div>
        </div>
      )}
      <table className="lots lots--bikes">
        <thead>
          <tr className="bikes__head">
            <th colSpan={3} scope="col">
              {t("bikes.col.station")}
            </th>
            <th scope="col">{t("bikes.col.rent")}</th>
            <th scope="col">{t("bikes.col.go")}</th>
          </tr>
        </thead>
        <tbody>
          {results.map((s, i) => {
            const href = directionsUrl(lot, s, { travelMode: "walking" });
            return (
              <tr key={s.id} className="lots__row bikes__row">
                <td className="lots__no">{i + 1}</td>
                <td className="lots__sym">
                  <Symbol kind="station" />
                </td>
                <td className="lots__main">
                  <a className="lots__open bikes__name" href={href} target="_blank" rel="noreferrer">
                    {s.name}
                    <span className="sr-only"> {"—"} {t("bikes.goLabel", { name: s.name })}</span>
                  </a>
                  <div className="lots__meta">
                    <span>{t("walk.straight", { d: formatDistance(s.distance_m) })}</span>
                  </div>
                </td>
                <td className="lots__spaces">
                  <BikeCell station={s} now={now} />
                </td>
                <td className="bikes__go">
                  <a className="bikes__go-link" href={href} target="_blank" rel="noreferrer" tabIndex={-1} aria-hidden="true">
                    <GoIcon />
                    {t("bikes.go")}
                  </a>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="attrib">{t("bikes.note")}</p>
    </section>
  );
}
