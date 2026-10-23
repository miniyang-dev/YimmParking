import { afterEach, describe, expect, it } from "vitest";
import { parseRoute, serializeRoute, takeLaunchLocate } from "./route";

describe("takeLaunchLocate", () => {
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("is true once for the installed app's start URL and removes the flag", () => {
    window.history.replaceState(null, "", "/?locate=1");
    expect(takeLaunchLocate()).toBe(true);
    expect(window.location.search).toBe("");
    expect(takeLaunchLocate()).toBe(false); // a reload does not ask again
  });

  it("keeps the rest of the address", () => {
    window.history.replaceState(null, "", "/?locate=1&mode=distance");
    expect(takeLaunchLocate()).toBe(true);
    expect(window.location.search).toBe("?mode=distance");
  });

  it("does nothing for an ordinary visit", () => {
    window.history.replaceState(null, "", "/?q=%E5%B8%82%E5%BA%9C%E8%B7%AF1%E8%99%9F");
    expect(takeLaunchLocate()).toBe(false);
    expect(window.location.search).toBe("?q=%E5%B8%82%E5%BA%9C%E8%B7%AF1%E8%99%9F");
  });
});

describe("an opened street-parking segment", () => {
  it("round-trips through the address", () => {
    const route = parseRoute("?lat=25.0375&lng=121.5637&curb=taipei%3A1002053");
    expect(route.curb).toBe("taipei:1002053");
    expect(serializeRoute(route)).toBe("?lat=25.037500&lng=121.563700&curb=taipei%3A1002053");
  });

  it("gives way to an opened lot, so only one detail is ever named", () => {
    const route = parseRoute("?lat=25&lng=121&lot=taipei%3ATPE1&curb=taipei%3A1");
    expect([route.lot, route.curb]).toEqual(["taipei:TPE1", null]);
  });
});
