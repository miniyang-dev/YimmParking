import { describe, expect, it } from "vitest";
import { formatServiceTime } from "./lotText";

describe("formatServiceTime", () => {
  it("says a full day as a full day", () => {
    expect(formatServiceTime("00:00:00-23:59:59")).toBe("24 小時");
    expect(formatServiceTime("00:00-23:59")).toBe("24 小時");
    expect(formatServiceTime("0:00~24:00")).toBe("24 小時");
  });

  it("drops the seconds from other hours", () => {
    expect(formatServiceTime("07:00:00-23:00:00")).toBe("07:00-23:00");
  });

  it("leaves free text alone", () => {
    expect(formatServiceTime("週一至週五 08:00-20:00")).toBe("週一至週五 08:00-20:00");
    expect(formatServiceTime("")).toBe("");
  });
});
