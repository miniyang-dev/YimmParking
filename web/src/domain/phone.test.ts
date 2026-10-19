import { describe, expect, it } from "vitest";
import { dialable } from "./phone";

describe("dialable", () => {
  it("adds the 02 area code a local Taipei number leaves out", () => {
    expect(dialable("26550818")).toBe("0226550818");
    expect(dialable("2655-0818")).toBe("0226550818");
  });

  it("keeps numbers that already carry an area code or are mobile", () => {
    expect(dialable("0226550818")).toBe("0226550818");
    expect(dialable("(02)2754-6661")).toBe("0227546661");
    expect(dialable("02-2655-0818")).toBe("0226550818");
    expect(dialable("0912-345-678")).toBe("0912345678");
    expect(dialable("02-2345678")).toBe("022345678");
    expect(dialable("+886-2-2655-0818")).toBe("+886226550818");
  });

  it("dials the main number only, never the extension appended to it", () => {
    expect(dialable("2523-5000 #1138")).toBe("0225235000");
    expect(dialable("23215858#8938")).toBe("0223215858");
    expect(dialable("(02)27546661分機18")).toBe("0227546661");
    expect(dialable("2731-7288 #1632黃小姐")).toBe("0227317288");
    expect(dialable("27546661*123")).toBe("0227546661");
  });

  it("dials the first of several numbers", () => {
    expect(dialable("0912-34-5678；2655-0818")).toBe("0912345678");
    expect(dialable("26550818、0226550819")).toBe("0226550818");
    expect(dialable("2504-6290或(02)85082000")).toBe("0225046290");
  });

  it("gives no link for text it cannot read with confidence", () => {
    expect(dialable("")).toBeNull();
    expect(dialable("請洽管理室")).toBeNull();
    expect(dialable("1234567")).toBeNull();
    expect(dialable("02123456789")).toBeNull();
    expect(dialable("26550818 26550819")).toBeNull(); // two numbers run together
  });
});
