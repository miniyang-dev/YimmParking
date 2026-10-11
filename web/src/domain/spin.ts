/**
 * "What shall we eat today": a roulette over the rows currently on screen.
 *
 * The plan is computed up front so the outcome is decided once, by one random draw, and the
 * animation only reveals it. That keeps the result testable and independent of timer jitter.
 */
export interface SpinPlan {
  /** Row index highlighted at each step. The last entry is the chosen row. */
  order: number[];
  /** Milliseconds to wait before moving *to* each step (same length as `order`). */
  delays: number[];
}

const FIRST_DELAY_MS = 70;
const LAST_DELAY_MS = 280;

/**
 * @param count number of rows to choose from
 * @param rng returns a number in [0, 1); injectable for tests
 */
export function planSpin(count: number, rng: () => number = Math.random): SpinPlan | null {
  if (!Number.isInteger(count) || count <= 0) return null;

  const picked = Math.min(count - 1, Math.floor(rng() * count));
  if (count === 1) return { order: [0], delays: [0] };

  // Start somewhere random and run one full lap, then on to the chosen row, so the roulette never
  // looks like it always begins at the top.
  const start = Math.min(count - 1, Math.floor(rng() * count));
  const steps = count + ((picked - start + count) % count);

  const order: number[] = [];
  const delays: number[] = [];
  for (let i = 0; i <= steps; i += 1) {
    order.push((start + i) % count);
    const progress = i / steps;
    // Quadratic ease-out: fast at first, settling onto the final row.
    delays.push(Math.round(FIRST_DELAY_MS + (LAST_DELAY_MS - FIRST_DELAY_MS) * progress ** 2));
  }
  return { order, delays };
}
