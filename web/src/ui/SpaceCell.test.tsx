import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Availability } from "../domain/types";
import { I18nProvider } from "../i18n";
import { SpaceCell } from "./SpaceCell";

const NOW = new Date("2026-10-10T15:00:00Z");

const full = (freshness: Availability["freshness"]): Availability => ({
  state: "known",
  count: 0,
  observed_at: "2026-10-10T14:35:00Z",
  freshness,
  suspect: false,
  source: "city",
});

function cell(availability: Availability) {
  render(
    <I18nProvider initial="zh">
      <SpaceCell availability={availability} now={NOW} />
    </I18nProvider>,
  );
  return screen.getByRole("group");
}

describe("SpaceCell when full", () => {
  afterEach(cleanup);

  it("says 0 left for a fresh reading", () => {
    expect(cell(full("fresh")).textContent).toContain("0 位");
  });

  it("says how old the zero is for a stale reading", () => {
    const group = cell(full("stale"));
    expect(group.textContent).toContain("25 分鐘前");
    expect(group.getAttribute("aria-label")).toContain("25 分鐘前");
  });
});
