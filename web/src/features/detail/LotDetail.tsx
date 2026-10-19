import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError } from "../../api/client";
import { ageMinutes } from "../../domain/availability";
import { compassLabel } from "../../domain/compass";
import { formatDistance } from "../../domain/distance";
import {
  categoryCounts,
  filterFood,
  inCategory,
  ratingFloors,
  type FoodCategoryKey,
  type FoodSort,
} from "../../domain/food";
import { directionsUrl, type Coordinate } from "../../domain/maps";
import { dialable } from "../../domain/phone";
import { walkMinutes } from "../../domain/walk";
import type { Lot } from "../../domain/types";
import { BRAND_LABEL } from "../../domain/vendors";
import { useI18n } from "../../i18n";
import type { StringKey } from "../../i18n/strings";
import { useFood } from "../../state/queries";
import { useSpin } from "../../state/useSpin";
import { SpaceCell } from "../../ui/SpaceCell";
import { BikeSection } from "./BikeSection";
import { Symbol } from "../../ui/Symbol";
import { feeHeadline, symbolFor } from "../results/ResultSheet";

interface Props {
  lot: Lot;
  number: number;
  now: Date;
  /** Where the search started: every route in this view starts here. */
  origin: Coordinate;
  originLabel: string;
  onBack: () => void;
}

/** A schematic of direction only: the start triangle at the centre, the lot at its bearing. */
function CourseDiagram({ bearing }: { bearing: number }) {
  const radius = 44;
  const angle = (bearing * Math.PI) / 180;
  const cx = 60;
  const cy = 60;
  const x = cx + Math.sin(angle) * radius;
  const y = cy - Math.cos(angle) * radius;
  return (
    <svg className="course__svg" viewBox="0 0 120 120" role="img" aria-label={`${Math.round(bearing)}°`}>
      <circle cx={cx} cy={cy} r={radius} className="course__ring" />
      <circle cx={cx} cy={cy} r={radius / 2} className="course__ring course__ring--inner" />
      <path d="M60 6v10M60 6l-4 6M60 6l4 6" className="course__north" />
      <text x="60" y="20" className="course__n" textAnchor="middle">
        N
      </text>
      <line x1={cx} y1={cy} x2={x} y2={y} className="course__line" />
      <path d="M60 52 67 66H53z" className="course__start" />
      <circle cx={x} cy={y} r="9" className="course__ctl" />
      <circle cx={x} cy={y} r="4.6" className="course__ctl" />
    </svg>
  );
}

function Star() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" className="star">
      <path d="M12 2l3 6.5 7 .9-5.1 4.8 1.3 7L12 17.8 5.8 21.2l1.3-7L2 9.4l7-.9z" fill="currentColor" />
    </svg>
  );
}

/** One question in the options row: a short label, then its options in one frame. */
function FilterGroup({
  label,
  group,
  children,
}: {
  label: string;
  group: string;
  children: ReactNode;
}) {
  return (
    <div className="food__grp" role="group" aria-label={group}>
      <span className="food__grp-label" aria-hidden="true">
        {label}
      </span>
      <div className="food__seg">{children}</div>
    </div>
  );
}

const CATEGORY_LABEL: Record<FoodCategoryKey, StringKey> = {
  chinese: "food.category.chinese",
  japanese: "food.category.japanese",
  korean: "food.category.korean",
  thai: "food.category.thai",
  southeast_asian: "food.category.southeast_asian",
  western: "food.category.western",
  seafood: "food.category.seafood",
  cafe: "food.category.cafe",
  other: "food.category.other",
};

function FoodSection({
  lot,
  origin,
  originLabel,
}: {
  lot: Lot;
  origin: Coordinate;
  originLabel: string;
}) {
  const { t } = useI18n();
  const query = useFood(lot.lat, lot.lng, origin, true);
  const [floorChoice, setFloorChoice] = useState<number | null>(null);
  const [sort, setSort] = useState<FoodSort>("walk");
  // null is every category. A category that has no places at the current filter is treated as null.
  const [categoryChoice, setCategoryChoice] = useState<FoodCategoryKey | null>(null);
  // Places the person has crossed out for today. The roulette never lands on these.
  const [excluded, setExcluded] = useState<ReadonlySet<string>>(new Set());

  const all = query.data?.results;
  const applied = query.data?.min_rating ?? 0;
  const floors = ratingFloors(applied);
  const floor = floorChoice !== null && floors.includes(floorChoice) ? floorChoice : applied;
  const counts = useMemo(() => (all ? categoryCounts(all) : []), [all]);
  const category =
    categoryChoice !== null && counts.some((c) => c.key === categoryChoice) ? categoryChoice : null;
  const shown = useMemo(
    () => (all ? filterFood(inCategory(all, category), floor, sort) : []),
    [all, category, floor, sort],
  );

  // The rows the roulette may land on: everything on screen that is not crossed out.
  const eligible = useMemo(
    () => shown.flatMap((place, row) => (excluded.has(place.id) ? [] : [row])),
    [shown, excluded],
  );
  // Changing the filter, sort or lot cancels a running roulette.
  const spin = useSpin(eligible, `${lot.id}|${category ?? "all"}|${floor}|${sort}|${shown.length}`);
  const pickedPlace = spin.view.picked !== null ? shown[spin.view.picked] : undefined;

  function rejectPicked() {
    if (spin.view.picked === null || pickedPlace === undefined) return;
    const next = new Set(excluded);
    next.add(pickedPlace.id);
    setExcluded(next);
    // `eligible` has not re-rendered yet, so hand the roulette the remaining rows directly.
    spin.start(eligible.filter((row) => row !== spin.view.picked));
  }
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  useEffect(() => {
    if (spin.view.picked !== null) {
      rowRefs.current[spin.view.picked]?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [spin.view.picked]);

  let body;
  if (query.isPending) {
    body = <p className="note">{t("food.loading")}</p>;
  } else if (query.isError) {
    const code = query.error instanceof ApiError ? query.error.code : "";
    const message =
      code === "quota_exhausted"
        ? t("food.quota")
        : query.error instanceof ApiError && query.error.status === 503
          ? t("food.unconfigured")
          : t("food.error");
    body = (
      <p className="note" role="status">
        {message}
      </p>
    );
  } else if (query.data.results.length === 0) {
    body = <p className="note">{t("food.empty")}</p>;
  } else {
    body = (
      <>
        <div className="food__filters">
          <div className="food__chips" role="group" aria-label={t("food.category.label")}>
            <button
              type="button"
              className="food__chip"
              aria-pressed={category === null}
              onClick={() => setCategoryChoice(null)}
            >
              {t("food.category.all")}
              <span className="food__chip-count">{query.data.results.length}</span>
            </button>
            {counts.map(({ key, count }) => (
              <button
                key={key}
                type="button"
                className="food__chip"
                aria-pressed={category === key}
                onClick={() => setCategoryChoice(key)}
              >
                {t(CATEGORY_LABEL[key])}
                <span className="food__chip-count">{count}</span>
              </button>
            ))}
          </div>
          <div className="food__opts">
            <FilterGroup label={t("food.row.rating")} group={t("food.rating.label")}>
              {floors.map((value) => (
                <button
                  key={value}
                  type="button"
                  className="food__opt"
                  aria-pressed={floor === value}
                  onClick={() => setFloorChoice(value)}
                >
                  {t("food.rating.min", { n: value.toFixed(1) })}
                </button>
              ))}
            </FilterGroup>
            <FilterGroup label={t("food.row.sort")} group={t("food.sort.label")}>
              <button
                type="button"
                className="food__opt"
                aria-pressed={sort === "walk"}
                onClick={() => setSort("walk")}
              >
                {t("food.sort.walk")}
              </button>
              <button
                type="button"
                className="food__opt"
                aria-pressed={sort === "rating"}
                onClick={() => setSort("rating")}
              >
                {t("food.sort.rating")}
              </button>
            </FilterGroup>
          </div>
        </div>
        <p className="food__count">
          {t("food.matching", { shown: shown.length, total: query.data.results.length })}
        </p>
        <p className="food__note">
          {t("food.prefiltered", { rating: applied.toFixed(1), n: query.data.min_reviews })}
        </p>
        <p className="food__note">{t("food.navFrom", { origin: originLabel })}</p>

        {shown.length > 0 && (
          <div className="roulette">
            {eligible.length === 0 ? (
              <p className="note">{t("food.allExcluded")}</p>
            ) : (
              <div className={spin.view.picked !== null ? "roulette__pair" : undefined}>
                {spin.view.picked !== null && !spin.view.running && (
                  <button type="button" className="roulette__btn roulette__btn--solid" onClick={rejectPicked}>
                    {t("food.reject")}
                  </button>
                )}
                <button
                  type="button"
                  className="roulette__btn"
                  onClick={() => spin.start()}
                  disabled={spin.view.running}
                >
                  {spin.view.running
                    ? t("food.picking")
                    : spin.view.picked !== null
                      ? t("food.pickAgain")
                      : t("food.pick")}
                </button>
              </div>
            )}
            <p className="roulette__result" role="status" aria-live="polite">
              {pickedPlace ? t("food.picked", { name: pickedPlace.name }) : ""}
            </p>
            {excluded.size > 0 && (
              <p className="roulette__excluded">
                {t("food.excluded", { n: excluded.size })}{" "}
                <button type="button" className="textbtn" onClick={() => setExcluded(new Set())}>
                  {t("food.restore")}
                </button>
              </p>
            )}
          </div>
        )}

        {shown.length === 0 ? (
          <p className="note">
            {t("food.noMatch")}{" "}
            <button type="button" className="textbtn" onClick={() => setFloorChoice(null)}>
              {t("food.reset")}
            </button>
          </p>
        ) : (
          <table className="lots lots--food">
            <tbody>
              {shown.map((place, i) => {
                const state =
                  spin.view.picked === i
                    ? "picked"
                    : spin.view.head === i
                      ? "head"
                      : spin.view.passed.has(i)
                        ? "passed"
                        : "idle";
                return (
                  <tr
                    key={place.id}
                    ref={(el) => {
                      rowRefs.current[i] = el;
                    }}
                    className={`lots__row lots__row--${state}${excluded.has(place.id) ? " lots__row--excluded" : ""}`}
                    data-spin={state}
                  >
                    <td className="lots__no">{String.fromCharCode(65 + (i % 26))}</td>
                    <td className="lots__main">
                      <a
                        className="link"
                        href={directionsUrl(origin, place, { placeId: place.id })}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {place.name}
                        <span className="sr-only"> {"\u2014"} {t("food.openMap")}</span>
                      </a>
                      <div className="lots__meta">
                        {place.walk_seconds !== null ? (
                          <>
                            <b>{t("walk.min", { min: walkMinutes(place.walk_seconds) })}</b>
                            <span>{t("walk.straight", { d: formatDistance(place.distance_m) })}</span>
                          </>
                        ) : (
                          <b>{t("walk.straight", { d: formatDistance(place.distance_m) })}</b>
                        )}
                        {place.primary_type && <span>{place.primary_type}</span>}
                        {place.open_now !== null && (
                          <span>{place.open_now ? t("food.open") : t("food.closed")}</span>
                        )}
                      </div>
                    </td>
                    <td className="lots__rating">
                      {place.rating !== null ? (
                        <span className="rating">
                          <span>
                            <Star />
                            {place.rating.toFixed(1)}
                          </span>
                          {place.user_rating_count !== null && (
                            <small>{t("food.reviews", { n: place.user_rating_count })}</small>
                          )}
                        </span>
                      ) : (
                        <small className="rating__none">{t("food.noRating")}</small>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </>
    );
  }

  return (
    <section className="food" aria-labelledby="food-title">
      <h2 id="food-title" className="band band--other">
        <span>{t("food.title")}</span>
        <small>{t("food.from")}</small>
      </h2>
      {body}
      <p className="attrib">
        {t("food.attribution")} · {t("walk.source")}
      </p>
    </section>
  );
}

export function LotDetail({ lot, number, now, origin, originLabel, onBack }: Props) {
  const { t, locale } = useI18n();
  const a = lot.availability;
  const age = ageMinutes(a.observed_at, now);
  const distance = formatDistance(lot.distance_m);

  const warning =
    a.state !== "known"
      ? t("detail.none")
      : a.suspect
        ? t("detail.suspect")
        : a.freshness === "stale"
          ? t("detail.stale")
          : null;

  const dial = lot.phone ? dialable(lot.phone) : null;
  const facts: [string, string][] = [[t("detail.hours"), lot.service_time || "—"]];
  if (lot.total_car !== null && lot.total_car > 0) facts.push([t("detail.capacity"), String(lot.total_car)]);
  if (lot.ev_charging_spaces) facts.push([t("detail.ev"), String(lot.ev_charging_spaces)]);
  if (lot.accessible_spaces) facts.push([t("detail.access"), String(lot.accessible_spaces)]);
  if (lot.kind) facts.push([t("detail.kind"), lot.kind]);

  return (
    <article className="detail">
      <button type="button" className="back" onClick={onBack}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M15 5l-7 7 7 7" />
        </svg>
        {t("detail.back")}
      </button>

      <div className="ctl">
        <span className="ctl__no" aria-hidden="true">{number}</span>
        <div>
          <h2 className="ctl__name">{lot.name}</h2>
          <p className="ctl__sub">
            <Symbol kind={symbolFor(lot)} size={18} />
            <span>
              {lot.district}
              {lot.brand !== "other" && (
                <>
                  {" · "}
                  {lot.iparking ? `${t("brand.iparking")} ` : ""}
                  {t(BRAND_LABEL[lot.brand])}
                  {lot.brand_evidence === "phone" ? ` (${t("brand.byPhone")})` : ""}
                </>
              )}
            </span>
          </p>
        </div>
      </div>

      <div className="course">
        <CourseDiagram bearing={lot.bearing_deg} />
        <dl className="course__facts">
          {lot.walk_seconds !== null && (
            <div>
              <dt>{t("walk.source")}</dt>
              <dd className="course__big">
                {t("walk.min", { min: walkMinutes(lot.walk_seconds) })}
              </dd>
              {lot.walk_meters !== null && (
                <dd className="course__sub">
                  {t("walk.route", { m: formatDistance(lot.walk_meters) })}
                </dd>
              )}
            </div>
          )}
          <div>
            <dt>{t("course.straight")}</dt>
            <dd className="course__big">
              {distance} {compassLabel(lot.bearing_deg, locale)}
            </dd>
          </div>
          <div>
            <dt>{t("detail.fee")}</dt>
            <dd>{feeHeadline(lot, t)}</dd>
          </div>
        </dl>
      </div>

      <div className="spaces">
        <SpaceCell availability={a} now={now} />
        <p className="spaces__text">
          {age !== null && a.state === "known" ? t("spaces.ago", { min: age }) : ""}
          {warning && <span className="spaces__warn">{warning}</span>}
        </p>
      </div>

      <a
        className="go"
        href={directionsUrl(origin, lot, { travelMode: "driving" })}
        target="_blank"
        rel="noreferrer"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3 11l18-8-8 18-2-8-8-2z" />
        </svg>
        {t("detail.navigate")}
      </a>
      <p className="go__from">{t("detail.navFrom", { origin: originLabel })}</p>


      <BikeSection key={`bikes-${lot.id}`} lot={lot} now={now} />

      <FoodSection key={lot.id} lot={lot} origin={origin} originLabel={originLabel} />

      <details className="fee">
        <summary>{t("detail.fee")}</summary>
        <p>{lot.fee_text || t("fee.unknown")}</p>
      </details>

      <dl className="facts">
        {facts.map(([label, value]) => (
          <div className="facts__row" key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
        {lot.phone && (
          <div className="facts__row">
            <dt>{t("detail.phone")}</dt>
            <dd>
              {dial ? (
                <a className="link link--plain" href={`tel:${dial}`}>
                  {lot.phone}
                </a>
              ) : (
                lot.phone
              )}
            </dd>
          </div>
        )}
      </dl>

    </article>
  );
}
