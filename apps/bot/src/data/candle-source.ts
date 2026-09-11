import { createReadStream } from "node:fs";
import { createInterface } from "node:readline";
import { CandleSchema, type Candle } from "../types.js";

/**
 * Where a strategy's candles come from. `AsyncIterable` rather than
 * `Candle[]` deliberately: historical replay (`NdjsonCandleSource`) can
 * yield immediately, but Phase 2 feeds this same engine from a live feed
 * that yields as bars close — `StrategyEngine.run()`'s `for await` loop is
 * identical either way, so the engine never needs to know which one it has.
 */
export interface DataSource {
  candles(): AsyncIterable<Candle>;
}

/**
 * Reads newline-delimited JSON candles produced by
 * `data/pipelines/scripts/export_trades_for_bot.py`, which drives the real
 * `ingestion.historical_loader.load_trades()` against Horizon and
 * aggregates trades into OHLCV bars — this is the historical-data reuse
 * path, not a parallel reimplementation of Horizon ingestion in TypeScript.
 */
export class NdjsonCandleSource implements DataSource {
  constructor(private readonly path: string) {}

  async *candles(): AsyncIterable<Candle> {
    const rl = createInterface({
      input: createReadStream(this.path, "utf-8"),
      crlfDelay: Infinity,
    });
    for await (const line of rl) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      yield CandleSchema.parse(JSON.parse(trimmed));
    }
  }
}
