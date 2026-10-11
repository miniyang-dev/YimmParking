import { describe, expect, it } from "vitest";
import { directionsUrl } from "./maps";

const ORIGIN = { lat: 25.05, lng: 121.5493 };
const LOT = { lat: 25.0512, lng: 121.5501 };

describe("directionsUrl", () => {
  it("starts from the searched place and ends at the chosen one", () => {
    const url = new URL(directionsUrl(ORIGIN, LOT));
    expect(url.origin + url.pathname).toBe("https://www.google.com/maps/dir/");
    expect(url.searchParams.get("api")).toBe("1");
    expect(url.searchParams.get("origin")).toBe("25.050000,121.549300");
    expect(url.searchParams.get("destination")).toBe("25.051200,121.550100");
  });

  it("adds the place id so Maps can name the destination", () => {
    const url = new URL(directionsUrl(ORIGIN, LOT, { placeId: "ChIJabc" }));
    expect(url.searchParams.get("destination_place_id")).toBe("ChIJabc");
    // The coordinate stays: the place-id parameter is documented as an addition to `destination`.
    expect(url.searchParams.get("destination")).toBe("25.051200,121.550100");
  });

  it("sets the travel mode only when asked", () => {
    expect(new URL(directionsUrl(ORIGIN, LOT)).searchParams.has("travelmode")).toBe(false);
    expect(
      new URL(directionsUrl(ORIGIN, LOT, { travelMode: "driving" })).searchParams.get("travelmode"),
    ).toBe("driving");
  });

  it("leaves the id out when there is none", () => {
    expect(
      new URL(directionsUrl(ORIGIN, LOT, { placeId: null })).searchParams.has("destination_place_id"),
    ).toBe(false);
  });
});
