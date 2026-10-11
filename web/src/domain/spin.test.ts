import { describe, expect, it } from "vitest";
import { planSpin } from "./spin";

/** A deterministic rng that replays the given values. */
const seq = (...values: number[]) => {
  let i = 0;
  return () => values[i++ % values.length] as number;
};

describe("planSpin", () => {
  it("has nothing to plan for an empty or invalid list", () => {
    expect(planSpin(0)).toBeNull();
    expect(planSpin(-3)).toBeNull();
    expect(planSpin(2.5)).toBeNull();
  });

  it("picks the only row at once", () => {
    expect(planSpin(1)).toEqual({ order: [0], delays: [0] });
  });

  it("always ends on the row the first random draw chose", () => {
    for (let picked = 0; picked < 7; picked += 1) {
      for (let start = 0; start < 7; start += 1) {
        const plan = planSpin(7, seq((picked + 0.5) / 7, (start + 0.5) / 7));
        expect(plan?.order.at(-1)).toBe(picked);
        expect(plan?.order[0]).toBe(start);
      }
    }
  });

  it("passes over every row at least once before settling", () => {
    const plan = planSpin(9, seq(0.3, 0.8));
    expect(new Set(plan?.order).size).toBe(9);
  });

  it("slows down as it settles", () => {
    const plan = planSpin(12, seq(0.5, 0.1));
    const delays = plan?.delays ?? [];
    expect(delays.length).toBeGreaterThan(12);
    for (let i = 1; i < delays.length; i += 1) {
      expect(delays[i]).toBeGreaterThanOrEqual(delays[i - 1] as number);
    }
    expect(delays.at(-1)).toBeGreaterThan(delays[0] as number);
  });

  it("is roughly uniform over many spins", () => {
    const counts = new Array<number>(5).fill(0);
    for (let i = 0; i < 5000; i += 1) {
      const row = planSpin(5)?.order.at(-1) as number;
      counts[row] = (counts[row] as number) + 1;
    }
    for (const c of counts) expect(c).toBeGreaterThan(800); // expected 1000 each
  });
});
