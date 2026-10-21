import { describe, expect, it } from "vitest";
import { staleForList, taipeiTime, type StaleSource } from "./cities";
import type { Lot } from "./types";

const lot = (city: Lot["city"]) => ({ city }) as Lot;
const TAIPEI: StaleSource = { city: "taipei", as_of: "2026-10-19T02:26:00Z" };
const NEW_TAIPEI: StaleSource = { city: "new_taipei", as_of: null };

describe("staleForList", () => {
  it("mentions only the stopped cities that have a lot in the list", () => {
    expect(staleForList([TAIPEI, NEW_TAIPEI], [lot("new_taipei")])).toEqual([NEW_TAIPEI]);
    expect(staleForList([TAIPEI], [lot("new_taipei")])).toEqual([]);
    expect(staleForList([TAIPEI, NEW_TAIPEI], [lot("taipei"), lot("new_taipei")])).toEqual([
      TAIPEI,
      NEW_TAIPEI,
    ]);
  });
});

describe("taipeiTime", () => {
  it("shows Taipei time whatever the device zone", () => {
    expect(taipeiTime("2026-10-19T02:26:00Z")).toBe("10/19 10:26");
    expect(taipeiTime("2026-12-31T16:05:00Z")).toBe("01/01 00:05");
  });
});
