import { describe, expect, it } from "vitest";
import { crossesAbove, crossesBelow, SmaIndicator } from "../src/strategy/indicators.js";

describe("SmaIndicator", () => {
  it("returns undefined until the window fills, then the correct average", () => {
    const sma = new SmaIndicator(3);
    expect(sma.update(10)).toBeUndefined();
    expect(sma.update(20)).toBeUndefined();
    expect(sma.update(30)).toBe(20); // (10+20+30)/3
    expect(sma.update(60)).toBeCloseTo(110 / 3, 10); // window slides to [20,30,60]
  });

  it("slides the window correctly on the 4th+ update", () => {
    const sma = new SmaIndicator(3);
    sma.update(10);
    sma.update(20);
    sma.update(30);
    // window is now [20, 30, 40]
    expect(sma.update(40)).toBeCloseTo(30, 10);
    // window is now [30, 40, 50]
    expect(sma.update(50)).toBeCloseTo(40, 10);
  });
});

describe("crossesAbove / crossesBelow", () => {
  it("detects an upward cross", () => {
    expect(crossesAbove(5, 10, 12, 10)).toBe(true);
    expect(crossesAbove(15, 10, 12, 10)).toBe(false); // was already above
  });

  it("detects a downward cross", () => {
    expect(crossesBelow(15, 10, 8, 10)).toBe(true);
    expect(crossesBelow(5, 10, 8, 10)).toBe(false); // was already below
  });

  it("returns false while either value is undefined", () => {
    expect(crossesAbove(undefined, 10, 12, 10)).toBe(false);
    expect(crossesBelow(15, 10, undefined, 10)).toBe(false);
  });
});
