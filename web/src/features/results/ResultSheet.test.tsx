import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Lot } from "../../domain/types";
import { I18nProvider } from "../../i18n";
import { ResultSheet } from "./ResultSheet";

const lot = (id: string, name: string): Lot => ({
  id,
  name,
  city: "taipei",
  district: "信義區",
  address: "",
  lat: 25.04,
  lng: 121.56,
  distance_m: 200,
  walk_seconds: null,
  walk_meters: null,
  bearing_deg: 90,
  brand: "other",
  brand_evidence: "none",
  iparking: false,
  vendor: null,
  block: "other",
  total_car: 100,
  availability: { state: "known", count: 12, observed_at: null, freshness: "unknown", suspect: false, source: "city" },
  fee_text: "",
  hourly_rate: 40,
  service_time: "",
  phone: "",
  kind: "",
  ev_charging_spaces: null,
  accessible_spaces: null,
  trend: null,
  doubts: [],
  hours: { status: "unknown", opens_at: null, closes_at: null },
});

function sheet(activeId?: string) {
  render(
    <I18nProvider initial="zh">
      <ResultSheet
        lots={[lot("a", "甲停車場"), lot("b", "乙停車場")]}
        mode="tiered"
        now={new Date("2026-10-23T09:00:00Z")}
        poolSize={2}
        walking="google"
        activeId={activeId}
        onOpen={() => {}}
      />
    </I18nProvider>,
  );
}

describe("ResultSheet", () => {
  afterEach(cleanup);

  it("marks the lot shown beside the sheet as the current one", () => {
    sheet("b");
    const row = screen.getByText("乙停車場").closest("tr");
    expect(row).toHaveAttribute("aria-current", "true");
    expect(row).toHaveClass("lots__row--active");
    expect(screen.getByText("甲停車場").closest("tr")).not.toHaveAttribute("aria-current");
  });

  it("marks nothing on a narrow screen", () => {
    sheet(undefined);
    expect(document.querySelector("[aria-current]")).toBeNull();
  });
});
