import { ageMinutes } from "../../domain/availability";
import { compassLabel } from "../../domain/compass";
import { formatDistance } from "../../domain/distance";
import { hoursPhrase } from "../../domain/insight";
import { feePhrase } from "../../domain/lotText";
import { directionsUrl, type Coordinate } from "../../domain/maps";
import { dialable } from "../../domain/phone";
import type { Lot } from "../../domain/types";
import { BRAND_LABEL } from "../../domain/vendors";
import { walkMinutes } from "../../domain/walk";
import { useI18n } from "../../i18n";
import { symbolFor } from "../../ui/lotSymbol";
import { SpaceCell } from "../../ui/SpaceCell";
import { Symbol } from "../../ui/Symbol";
import { BikeSection } from "./BikeSection";
import { CourseDiagram } from "./CourseDiagram";
import { FoodSection } from "./FoodSection";
import { Movement } from "./Movement";
import { ShareButton } from "./ShareButton";
import { TypicalDay } from "./TypicalDay";

interface Props {
  lot: Lot;
  number: number;
  now: Date;
  /** Where the search started: every route in this view starts here. */
  origin: Coordinate;
  originLabel: string;
  onBack: () => void;
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
  const hours = hoursPhrase(lot.hours);
  const fee = feePhrase(lot);
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
            <dd>{t(fee.key, fee.vars)}</dd>
          </div>
        </dl>
      </div>

      <div className="spaces">
        <SpaceCell availability={a} now={now} />
        <p className="spaces__text">
          {age !== null && a.state === "known" ? t("spaces.ago", { min: age }) : ""}
          {warning && <span className="spaces__warn">{warning}</span>}
          {hours && <span className="spaces__hours">{t(hours.key, hours.vars)}</span>}
          {a.source === "tdx" && <span className="spaces__warn">{t("source.tdxLot")}</span>}
        </p>
      </div>

      <Movement lot={lot} />

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
      <ShareButton title={lot.name} text={[lot.name, lot.address].filter(Boolean).join("・")} />

      <TypicalDay key={`typical-${lot.id}`} lotId={lot.id} now={now} />


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
