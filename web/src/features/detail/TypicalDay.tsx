import { useState } from "react";
import { clockOf, niceMax, taipeiSlot } from "../../domain/insight";
import { useI18n } from "../../i18n";
import type { StringKey } from "../../i18n/strings";
import { useTypicalDay } from "../../state/queries";

const W = 336;
const H = 132;
const PAD_LEFT = 30;
const PAD_TOP = 14;
const PAD_BOTTOM = 18;
const PLOT_H = H - PAD_TOP - PAD_BOTTOM;
const SLOT_MIN = 30;

/** Top-rounded column, square at the baseline. */
function column(x: number, width: number, top: number, bottom: number): string {
  const r = Math.min(2, width / 2, bottom - top);
  return `M${x} ${bottom}V${top + r}Q${x} ${top} ${x + r} ${top}H${x + width - r}Q${x + width} ${top} ${x + width} ${top + r}V${bottom}Z`;
}

/**
 * A lot's usual spaces through today's weekday: one ink column per half hour, the current one
 * darker. A half hour without enough past days is left empty rather than drawn as zero.
 */
export function TypicalDay({ lotId, now }: { lotId: string; now: Date }) {
  const { t } = useI18n();
  const query = useTypicalDay(lotId);
  const [picked, setPicked] = useState<number | null>(null);

  let body;
  if (query.isPending) {
    body = <p className="note">{t("typical.loading")}</p>;
  } else if (query.isError) {
    body = <p className="note">{t("typical.error")}</p>;
  } else {
    const data = query.data;
    const day = t(`weekday.${data.weekday}` as StringKey);
    const values = data.slots.map((s) => s.median).filter((v): v is number => v !== null);
    if (values.length === 0) {
      body = (
        <p className="note">{t("typical.waiting", { n: data.days_used, day, min: data.min_days })}</p>
      );
    } else {
      const max = niceMax(Math.max(...values));
      const slotW = (W - PAD_LEFT) / data.slots.length;
      const barW = Math.min(24, slotW - 2);
      const baseline = PAD_TOP + PLOT_H;
      const y = (v: number) => baseline - (v / max) * PLOT_H;
      const nowIndex = taipeiSlot(now, SLOT_MIN) / SLOT_MIN;
      const focus = picked ?? nowIndex;
      const focused = data.slots[focus];
      const readout =
        focused && focused.median !== null
          ? t("typical.readout", {
              time: clockOf(focused.minute),
              n: Math.round(focused.median),
              days: focused.samples,
            })
          : t("typical.noValue", { time: clockOf(focused?.minute ?? 0) });

      body = (
        <>
          <svg
            className="typical__chart"
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label={t("typical.title", { day })}
            onPointerLeave={() => setPicked(null)}
          >
            <line x1={PAD_LEFT} x2={W} y1={PAD_TOP} y2={PAD_TOP} className="typical__grid" />
            <line x1={PAD_LEFT} x2={W} y1={baseline} y2={baseline} className="typical__base" />
            <text x={PAD_LEFT - 4} y={PAD_TOP + 4} className="typical__tick" textAnchor="end">
              {max}
            </text>
            <text x={PAD_LEFT - 4} y={baseline} className="typical__tick" textAnchor="end">
              0
            </text>
            {[0, 6, 12, 18, 24].map((hour) => (
              <text
                key={hour}
                x={PAD_LEFT + ((hour * 60) / SLOT_MIN) * slotW}
                y={H - 4}
                className="typical__tick"
                textAnchor={hour === 0 ? "start" : hour === 24 ? "end" : "middle"}
              >
                {hour}
              </text>
            ))}
            {data.slots.map((slot, i) => {
              const x = PAD_LEFT + i * slotW + (slotW - barW) / 2;
              const state = i === focus ? "typical__bar--focus" : i === nowIndex ? "typical__bar--now" : "";
              return (
                <g key={slot.minute}>
                  {slot.median !== null && slot.median > 0 && (
                    <path d={column(x, barW, y(slot.median), baseline)} className={`typical__bar ${state}`} />
                  )}
                  {/* The hit target is the whole column of the slot, not just the bar. */}
                  <rect
                    x={PAD_LEFT + i * slotW}
                    y={0}
                    width={slotW}
                    height={baseline}
                    fill="transparent"
                    onPointerEnter={() => setPicked(i)}
                    onClick={() => setPicked(i)}
                  />
                </g>
              );
            })}
            <text
              x={PAD_LEFT + (nowIndex + 0.5) * slotW}
              y={PAD_TOP - 4}
              className="typical__now"
              textAnchor="middle"
            >
              {t("typical.now")}
            </text>
          </svg>
          <p className="typical__readout" aria-live="polite">
            {readout}
          </p>
          <p className="typical__hint">{t("typical.hint", { day })}</p>
          <details className="typical__table">
            <summary>{t("typical.table")}</summary>
            <table>
              <thead>
                <tr>
                  <th scope="col">{t("typical.col.time")}</th>
                  <th scope="col">{t("typical.col.median")}</th>
                  <th scope="col">{t("typical.col.days")}</th>
                </tr>
              </thead>
              <tbody>
                {data.slots
                  .filter((s) => s.median !== null)
                  .map((s) => (
                    <tr key={s.minute}>
                      <td>{clockOf(s.minute)}</td>
                      <td>{Math.round(s.median as number)}</td>
                      <td>{s.samples}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </details>
        </>
      );
    }
  }

  const title = query.data
    ? t("typical.title", { day: t(`weekday.${query.data.weekday}` as StringKey) })
    : t("typical.loading");
  return (
    <section className="typical" aria-labelledby="typical-title">
      <h2 id="typical-title" className="band band--other">
        <span>{title}</span>
      </h2>
      {body}
    </section>
  );
}
