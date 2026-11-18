import { describe, expect, it } from "vitest";
import { addDays, fmtMoney, fmtPct, fmtNum } from "@/utils/format";
import { qs } from "@/services/api";
import { passwordProblems } from "@/pages/AuthPages";

describe("formatting", () => {
  it("formats money, percentages and numbers", () => {
    expect(fmtMoney(1234.5)).toBe("$1,235");
    expect(fmtMoney(1234.5, true)).toBe("$1,234.50");
    expect(fmtMoney(null)).toBe("–");
    expect(fmtPct(2.345)).toBe("+2.3%");
    expect(fmtPct(-4)).toBe("-4.0%");
    expect(fmtPct(null)).toBe("n/a");
    expect(fmtNum(1234567)).toBe("1,234,567");
  });
  it("shifts ISO dates across month boundaries", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });
});

describe("query strings", () => {
  it("skips empty values and joins arrays", () => {
    expect(qs({ start: "2026-01-01", stores: [1, 2], categories: [], q: "", x: null })).toBe("?start=2026-01-01&stores=1%2C2");
    expect(qs({})).toBe("");
  });
});

describe("password rules (mirror the backend)", () => {
  it("rejects weak passwords", () => {
    expect(passwordProblems("short1")).not.toBeNull();
    expect(passwordProblems("lettersonly")).not.toBeNull();
    expect(passwordProblems("Passw0rd!")).toBeNull();
  });
});
