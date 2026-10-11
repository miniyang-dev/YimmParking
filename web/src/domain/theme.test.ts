import { describe, expect, it } from "vitest";
import { nextTheme, parseTheme, themeColor } from "./theme";

describe("theme", () => {
  it("defaults to light for anything it does not recognise", () => {
    expect(parseTheme(null)).toBe("light");
    expect(parseTheme(undefined)).toBe("light");
    expect(parseTheme("sepia")).toBe("light");
    expect(parseTheme("")).toBe("light");
  });

  it("keeps the two other valid choices", () => {
    expect(parseTheme("dark")).toBe("dark");
    expect(parseTheme("auto")).toBe("auto");
    expect(parseTheme("light")).toBe("light");
  });

  it("cycles light, dark, auto and back", () => {
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("auto");
    expect(nextTheme("auto")).toBe("light");
  });

  it("follows the system only in auto", () => {
    expect(themeColor("light", true)).toBe("#ffffff");
    expect(themeColor("dark", false)).toBe("#14171a");
    expect(themeColor("auto", true)).toBe("#14171a");
    expect(themeColor("auto", false)).toBe("#ffffff");
  });
});
