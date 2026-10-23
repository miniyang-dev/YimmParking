import { bearingDeg, compassLabel } from "../../domain/compass";
import { curbNotes } from "../../domain/curb";
import { formatDistance } from "../../domain/distance";
import { directionsUrl, type Coordinate } from "../../domain/maps";
import type { CurbSegment } from "../../domain/types";
import { useI18n } from "../../i18n";
import { useCurb } from "../../state/queries";
import { CurbCountCell } from "../results/CurbSection";
import { BikeSection } from "./BikeSection";
import { CourseDiagram } from "./CourseDiagram";
import { FoodSection } from "./FoodSection";

interface Props {
  segment: CurbSegment;
  /** The segment's letter in the street-parking list. */
  letter: string;
  now: Date;
  /** Where the search started: the route and the food walking times start here. */
  origin: Coordinate;
  originLabel: string;
  /** Absent on wide screens, where the sheet stays beside the detail. */
  onBack?: () => void;
}

/** A street-parking segment opened like a lot: count, the way there, YouBike and food nearby. */
export function CurbDetail({ segment, letter, now, origin, originLabel, onBack }: Props) {
  const { t, locale } = useI18n();
  const bearing = bearingDeg(origin, segment);
  const notes = curbNotes(segment, now);

  return (
    <article className="detail">
      <div className="detail__main">
        {onBack && <BackButton onBack={onBack} />}

        <div className="ctl">
          <span className="ctl__no" aria-hidden="true">{letter}</span>
          <div>
            <h2 className="ctl__name">{segment.name}</h2>
            <p className="ctl__sub">
              <span>{[t("curb.kind"), segment.town].filter(Boolean).join(" · ")}</span>
            </p>
          </div>
        </div>

        <div className="course">
          <CourseDiagram bearing={bearing} />
          <dl className="course__facts">
            <div>
              <dt>{t("course.straight")}</dt>
              <dd className="course__big">
                {formatDistance(segment.distance_m)} {compassLabel(bearing, locale)}
              </dd>
            </div>
            <div>
              <dt>{t("detail.fee")}</dt>
              <dd>{segment.fare || t("fee.unknown")}</dd>
            </div>
          </dl>
        </div>

        <div className="spaces">
          <CurbCountCell segment={segment} />
          <p className="spaces__text">
            {notes.map((note) => (
              <span key={note.key} className="spaces__warn">
                {t(note.key, note.vars)}
              </span>
            ))}
          </p>
        </div>

        <a
          className="go"
          href={directionsUrl(origin, segment, { travelMode: "driving" })}
          target="_blank"
          rel="noreferrer"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 11l18-8-8 18-2-8-8-2z" />
          </svg>
          {t("detail.navigate")}
        </a>
        <p className="go__from">{t("detail.navFrom", { origin: originLabel })}</p>
      </div>

      <div className="detail__side">
        <BikeSection key={`bikes-${segment.id}`} lot={segment} now={now} />
        <FoodSection key={segment.id} lot={segment} origin={origin} originLabel={originLabel} />
      </div>

      <div className="detail__tail">
        {segment.description && segment.description !== segment.name && (
          <dl className="facts">
            <div className="facts__row">
              <dt>{t("curb.segment")}</dt>
              <dd>{segment.description}</dd>
            </div>
          </dl>
        )}
        <p className="attrib">{t("curb.note")}</p>
      </div>
    </article>
  );
}

function BackButton({ onBack }: { onBack: () => void }) {
  const { t } = useI18n();
  return (
    <button type="button" className="back" onClick={onBack}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M15 5l-7 7 7 7" />
      </svg>
      {t("detail.back")}
    </button>
  );
}

/**
 * The segment named in the address, found in this search's street-parking answer (the list
 * already asked for it, so this is read from the cache, not from TDX again).
 */
export function OpenedCurb({
  id,
  now,
  origin,
  originLabel,
  onBack,
  onClose,
}: Omit<Props, "segment" | "letter"> & { id: string; onClose: () => void }) {
  const { t } = useI18n();
  const query = useCurb(origin.lat, origin.lng);
  if (query.isPending) {
    return (
      <p className="sr-only" role="status">
        {t("loading")}
      </p>
    );
  }
  const results = query.data?.results ?? [];
  const index = results.findIndex((segment) => segment.id === id);
  const segment = results[index];
  if (!segment) {
    return (
      <p className="notice" role="alert">
        {t("curb.notFound")}{" "}
        <button type="button" className="textbtn" onClick={onClose}>
          {t("detail.back")}
        </button>
      </p>
    );
  }
  return (
    <CurbDetail
      segment={segment}
      letter={String.fromCharCode(97 + (index % 26))}
      now={now}
      origin={origin}
      originLabel={originLabel}
      onBack={onBack}
    />
  );
}
