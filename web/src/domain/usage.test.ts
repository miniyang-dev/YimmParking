import { describe, expect, it } from "vitest";
import { USAGE_LABEL, usagePercent } from "./usage";

describe("usage", () => {
  it("shows one decimal and clamps to the limit", () => {
    expect(usagePercent(8, 900)).toBe(0.9);
    expect(usagePercent(0, 9000)).toBe(0);
    expect(usagePercent(9500, 9000)).toBe(100);
    expect(usagePercent(5, 0)).toBe(0);
  });

  it("labels meters by what they do, never by the provider's product name", () => {
    expect(Object.values(USAGE_LABEL).every((key) => key.startsWith("usage."))).toBe(true);
    expect(USAGE_LABEL["unknown_meter"]).toBeUndefined();
  });
});
