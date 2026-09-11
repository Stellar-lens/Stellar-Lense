import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { NdjsonCandleSource } from "../src/data/candle-source.js";

describe("NdjsonCandleSource", () => {
  it("parses the committed fixture into well-formed candles", async () => {
    const source = new NdjsonCandleSource("fixtures/xlm-usdc-5m.ndjson");
    const candles = [];
    for await (const candle of source.candles()) {
      candles.push(candle);
    }
    expect(candles.length).toBeGreaterThan(10);
    for (const c of candles) {
      expect(c.high).toBeGreaterThanOrEqual(c.low);
      expect(typeof c.time).toBe("string");
    }
  });

  it("skips blank lines and preserves order", async () => {
    const dir = mkdtempSync(join(tmpdir(), "bot-candles-"));
    const path = join(dir, "candles.ndjson");
    const lines = [
      JSON.stringify({ time: "t0", open: 1, high: 2, low: 1, close: 1.5, volume: 10, trades: 3 }),
      "",
      JSON.stringify({ time: "t1", open: 1.5, high: 2, low: 1, close: 1.8, volume: 8, trades: 2 }),
    ];
    writeFileSync(path, lines.join("\n"));

    const source = new NdjsonCandleSource(path);
    const candles = [];
    for await (const candle of source.candles()) {
      candles.push(candle);
    }
    expect(candles.map((c) => c.time)).toEqual(["t0", "t1"]);
  });
});
