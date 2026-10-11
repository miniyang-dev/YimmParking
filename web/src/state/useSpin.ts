import { useCallback, useEffect, useRef, useState } from "react";
import { planSpin } from "../domain/spin";

export interface SpinView {
  running: boolean;
  /** The row the roulette is on right now (only while running). */
  head: number | null;
  /** Every row the roulette has moved over so far. */
  passed: ReadonlySet<number>;
  /** The chosen row, once the roulette has stopped. */
  picked: number | null;
}

const IDLE: SpinView = { running: false, head: null, passed: new Set(), picked: null };

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Drives the roulette over a set of row indices (`rows`), so rows the person has crossed out are
 * simply never visited. `resetKey` identifies the list being spun: when it changes (filter or sort
 * changed, another lot opened) the roulette is cancelled, because its row indices no longer mean
 * the same places.
 */
export function useSpin(
  rows: readonly number[],
  resetKey: string,
  rng: () => number = Math.random,
) {
  const [view, setView] = useState<SpinView>(IDLE);
  const timer = useRef<number | null>(null);

  const cancel = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    cancel();
    setView(IDLE);
  }, [cancel]);

  useEffect(() => {
    reset();
    return cancel;
  }, [resetKey, reset, cancel]);

  /** Start a spin. `override` lets a caller spin over rows that are not yet in `rows` state. */
  const start = useCallback(
    (override?: readonly number[]) => {
      cancel();
      const candidates = override ?? rows;
      const plan = planSpin(candidates.length, rng);
      if (!plan) {
        setView(IDLE);
        return;
      }
      const order = plan.order.map((i) => candidates[i] as number);
      const finalRow = order[order.length - 1] as number;

      if (prefersReducedMotion() || order.length === 1) {
        setView({ running: false, head: null, passed: new Set(), picked: finalRow });
        return;
      }

      const passed = new Set<number>();
      const step = (i: number) => {
        const row = order[i] as number;
        passed.add(row);
        const last = i === order.length - 1;
        setView({
          running: !last,
          head: last ? null : row,
          passed: new Set(passed),
          picked: last ? row : null,
        });
        if (!last) {
          timer.current = window.setTimeout(() => step(i + 1), plan.delays[i + 1]);
        }
      };
      step(0);
    },
    [rows, rng, cancel],
  );

  return { view, start, reset };
}
