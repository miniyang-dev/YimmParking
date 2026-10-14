import { describe, expect, it } from "vitest";
import { bearingDeg, bikeState } from "./bikes";
import type { BikeStation } from "./types";

const NOW = new Date("2026-10-14T11:20:00Z");

function station(over: Partial<BikeStation>): BikeStation {
  return {
    id: "taipei:1",
    name: "科技大樓站",
    address: "",
    lat: 25.026,
    lng: 121.5436,
    distance_m: 120,
    rent: 8,
    ret: 20,
    observed_at: "2026-10-14T11:19:00Z",
    ...over,
  };
}

describe("bikeState", () => {
  it("reads a recent count as known", () => {
    expect(bikeState(station({}), NOW)).toEqual({ kind: "known", rent: 8, ret: 20 });
  });

  it("keeps a real zero apart from no reading", () => {
    expect(bikeState(station({ rent: 0 }), NOW)).toEqual({ kind: "empty", ret: 20 });
    expect(bikeState(station({ rent: null }), NOW)).toEqual({ kind: "none" });
  });

  it("marks an old reading and says how old", () => {
    const old = station({ observed_at: "2026-10-14T11:02:00Z" });
    expect(bikeState(old, NOW)).toEqual({ kind: "stale", rent: 8, ret: 20, ageMin: 18 });
  });

  it("does not call a reading old when the feed gave no time", () => {
    expect(bikeState(station({ observed_at: null }), NOW).kind).toBe("known");
  });
});

describe("bearingDeg", () => {
  const origin = { lat: 25.0, lng: 121.5 };
  it("points the four ways", () => {
    expect(bearingDeg(origin, { lat: 25.01, lng: 121.5 })).toBeCloseTo(0, 0);
    expect(bearingDeg(origin, { lat: 25.0, lng: 121.51 })).toBeCloseTo(90, 0);
    expect(bearingDeg(origin, { lat: 24.99, lng: 121.5 })).toBeCloseTo(180, 0);
    expect(bearingDeg(origin, { lat: 25.0, lng: 121.49 })).toBeCloseTo(270, 0);
  });
});
