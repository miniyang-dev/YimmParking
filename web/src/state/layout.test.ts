import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useWide, WIDE_QUERY } from "./layout";

function fakeMatchMedia(initial: boolean) {
  const listeners = new Set<() => void>();
  const list = {
    matches: initial,
    media: WIDE_QUERY,
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => list));
  return {
    resize(wide: boolean) {
      list.matches = wide;
      listeners.forEach((fn) => fn());
    },
  };
}

describe("useWide", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("follows the desktop media query as the window is resized", () => {
    const media = fakeMatchMedia(false);
    const { result } = renderHook(() => useWide());
    expect(result.current).toBe(false);
    act(() => media.resize(true));
    expect(result.current).toBe(true);
    expect(window.matchMedia).toHaveBeenCalledWith("(min-width: 1024px)");
  });
});
