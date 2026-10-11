import { ageMinutes, spaceState } from "../domain/availability";
import type { Availability } from "../domain/types";
import { useI18n } from "../i18n";

interface Props {
  availability: Availability;
  now: Date;
}

/**
 * The "spaces left" cell. Each state is told apart by texture and text, not by colour alone:
 * known = plain numeral, stale = green hatch + age, full = black hatch, none = dot screen.
 */
export function SpaceCell({ availability, now }: Props) {
  const { t } = useI18n();
  const state = spaceState(availability);
  const age = ageMinutes(availability.observed_at, now);

  switch (state.kind) {
    case "full":
      return (
        <div className="cell cell--full" role="group" aria-label={`${t("spaces.full")}, ${t("spaces.fullHint")}`}>
          <b className="cell__num">{t("spaces.full")}</b>
          <span className="cell__sub">{t("spaces.fullHint")}</span>
        </div>
      );
    case "none":
      return (
        <div className="cell cell--none" role="group" aria-label={t("spaces.none")}>
          <b className="cell__word">{t("spaces.none")}</b>
        </div>
      );
    case "stale":
    case "known": {
      const sub =
        state.kind === "stale" && age !== null
          ? t("spaces.ago", { min: age })
          : state.suspect
            ? t("spaces.suspect")
            : t("spaces.unit");
      return (
        <div
          className={`cell ${state.kind === "stale" ? "cell--stale" : ""}`}
          role="group"
          aria-label={`${state.count} ${t("spaces.unit")}, ${sub}`}
        >
          <b className="cell__num">
            {state.suspect && <span className="cell__approx" aria-hidden="true">~</span>}
            {state.count}
          </b>
          <span className="cell__sub">{sub}</span>
        </div>
      );
    }
  }
}
