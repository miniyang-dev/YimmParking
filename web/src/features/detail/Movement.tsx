import { DOUBT_LONG, trendPhrases } from "../../domain/insight";
import type { Lot } from "../../domain/types";
import { useI18n } from "../../i18n";

/** Where the count has been heading, and any reason from the past week to doubt it. */
export function Movement({ lot }: { lot: Lot }) {
  const { t } = useI18n();
  const live = lot.availability.state === "known";
  if (!live && lot.doubts.length === 0) return null;
  const phrases = trendPhrases(lot.trend, { quiet: false });
  // No movement to report and nothing to doubt: a block saying so only pushes "navigate" down.
  if (phrases.length === 0 && lot.doubts.length === 0) return null;
  return (
    <section className="move" aria-labelledby="move-title">
      <h2 id="move-title" className="band band--other">
        <span>{t("trend.title")}</span>
      </h2>
      {live && phrases.length > 0 && (
        <p className="move__trend">{phrases.map((p) => t(p.key, p.vars)).join("，")}</p>
      )}
      {lot.doubts.map((doubt) => (
        <p key={doubt} className="move__doubt">
          {t(DOUBT_LONG[doubt])}
        </p>
      ))}
    </section>
  );
}
