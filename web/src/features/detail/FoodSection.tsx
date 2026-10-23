import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError } from "../../api/client";
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
import { walkMinutes } from "../../domain/walk";
import { useI18n } from "../../i18n";
import type { StringKey } from "../../i18n/strings";
import { useFood } from "../../state/queries";
import { useSpin } from "../../state/useSpin";

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

export function FoodSection({
  lot,
  origin,
  originLabel,
}: {
  /** What the food is near: a lot, or a street-parking segment. */
  lot: Coordinate & { id: string };
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
