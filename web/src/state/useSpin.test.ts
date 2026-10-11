import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSpin } from "./useSpin";

const seq = (...values: number[]) => {
  let i = 0;
  return () => values[i++ % values.length] as number;
};

const ROWS4 = [0, 1, 2, 3];

describe("useSpin", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("walks the rows, tinting each one it passes, and stops on the chosen row", () => {
    // count 4: picked = floor(0.8*4) = 3, start = floor(0*4) = 0 → 0,1,2,3,0,1,2,3
    const rng = seq(0.8, 0);
    const { result } = renderHook(() => useSpin(ROWS4, "k", rng));

    act(() => result.current.start());
    expect(result.current.view.running).toBe(true);
    expect(result.current.view.head).toBe(0);
    expect([...result.current.view.passed]).toEqual([0]);

    act(() => void vi.advanceTimersByTime(80));
    expect(result.current.view.head).toBe(1);
    expect([...result.current.view.passed].sort()).toEqual([0, 1]);

    act(() => void vi.advanceTimersByTime(10_000));
    expect(result.current.view.running).toBe(false);
    expect(result.current.view.picked).toBe(3);
    expect(result.current.view.head).toBeNull();
    expect(result.current.view.passed.size).toBe(4);
  });

  it("cancels when the list it was spinning changes", () => {
    const rng = seq(0.8, 0);
    const { result, rerender } = renderHook(({ k }) => useSpin(ROWS4, k, rng), {
      initialProps: { k: "a" },
    });
    act(() => result.current.start());
    act(() => void vi.advanceTimersByTime(100));
    expect(result.current.view.running).toBe(true);

    rerender({ k: "b" });
    expect(result.current.view.running).toBe(false);
    expect(result.current.view.picked).toBeNull();
    expect(result.current.view.passed.size).toBe(0);

    // The cancelled timer must not resurrect the old spin.
    act(() => void vi.advanceTimersByTime(10_000));
    expect(result.current.view.picked).toBeNull();
  });

  it("starting again clears the previous trail", () => {
    const { result } = renderHook(() => useSpin([0, 1, 2], "k", seq(0.5, 0.1)));
    act(() => result.current.start());
    act(() => void vi.advanceTimersByTime(10_000));
    expect(result.current.view.picked).not.toBeNull();

    act(() => result.current.start());
    expect(result.current.view.picked).toBeNull();
    expect(result.current.view.passed.size).toBe(1);
  });

  it("does nothing for an empty list", () => {
    const { result } = renderHook(() => useSpin([], "k"));
    act(() => result.current.start());
    expect(result.current.view.running).toBe(false);
    expect(result.current.view.picked).toBeNull();
  });

  it("only ever visits the rows it is given, so crossed-out rows are skipped", () => {
    // rows 1, 4, 6 are eligible out of 8; picked = floor(0.9*3) = 2 → row 6, start = floor(0*3) = 0 → row 1
    const { result } = renderHook(() => useSpin([1, 4, 6], "k", seq(0.9, 0)));
    act(() => result.current.start());
    act(() => void vi.advanceTimersByTime(10_000));

    expect(result.current.view.picked).toBe(6);
    expect([...result.current.view.passed].sort()).toEqual([1, 4, 6]);
  });

  it("can start over rows passed in at call time (used right after a row is crossed out)", () => {
    const { result } = renderHook(() => useSpin(ROWS4, "k", seq(0.1, 0)));
    act(() => result.current.start([2, 3]));
    act(() => void vi.advanceTimersByTime(10_000));
    expect([2, 3]).toContain(result.current.view.picked);
    expect(result.current.view.passed.has(0)).toBe(false);
    expect(result.current.view.passed.has(1)).toBe(false);
  });

  it("clears the picked row when there is nothing left to choose from", () => {
    const { result } = renderHook(() => useSpin(ROWS4, "k", seq(0.5, 0.5)));
    act(() => result.current.start());
    act(() => void vi.advanceTimersByTime(10_000));
    expect(result.current.view.picked).not.toBeNull();

    act(() => result.current.start([]));
    expect(result.current.view.picked).toBeNull();
    expect(result.current.view.running).toBe(false);
  });
});
